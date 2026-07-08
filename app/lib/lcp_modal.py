"""
Modal app that serves the per-annotator LCP model on a GPU.

Why this exists
---------------
The LCP model (a LoRA adapter on a ~2.5B-parameter Qwen base) is heavy to load
and wants a GPU to be fast. Instead of loading it inside every web/worker process, we run it
on Modal: one warm GPU container holds the model in memory and the FastAPI app
calls it remotely. See ``difficult_words_ml`` in ``app/lib/difficulty.py`` for
the caller.

Deploying
---------
1. One-time auth on this machine:  ``python3 -m modal setup``
2. Create the secret with the model config (see .env / config.py):
     modal secret create lcp-model \
       LCP_MODEL_DIR=<hub repo id or path> \
       LCP_MODEL_TOKEN=<hf token or ''> \
       LCP_MODEL_REVISION=<revision or ''>
3. Deploy:  ``modal deploy app/lib/lcp_modal.py``

After deploy the class is reachable from any process (with Modal creds) via
``modal.Cls.from_name(APP_NAME, "LCPModel")`` — that is what difficulty.py does.
"""

import os

import modal

APP_NAME = "fluidread-lcp"

# The image only needs what inference requires. Installing the package pulls its
# pinned torch/transformers/peft, which is exactly the versions the model was
# trained/saved with. Built once and cached by Modal, so build cost is paid once.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")  # debian_slim has no git; pip needs it for the URL below
    .pip_install("git+https://github.com/simoisweber/lexetta-lcp.git")
)

app = modal.App(APP_NAME)

# Persist the Hugging Face cache across cold starts so the adapter + base model
# weights are downloaded only the first time, not on every new container.
hf_cache = modal.Volume.from_name("fluidread-hf-cache", create_if_missing=True)
HF_CACHE_DIR = "/root/.cache/huggingface"


@app.cls(
    image=image,
    # ~2.5B params in bf16 is ~5 GB of weights. bf16 needs an Ampere-or-newer
    # GPU (T4 can't do it), so L4 (24 GB) is the cheapest fit with headroom for
    # activations on batched requests.
    gpu="L4",
    # Weights stream through CPU RAM on load; reserve enough to avoid OOM there.
    memory=16384,
    secrets=[modal.Secret.from_name("lcp-model")],
    volumes={HF_CACHE_DIR: hf_cache},
    # Keep a container warm for 5 min after the last call so bursts of page reads
    # reuse the loaded model. Raise, or set min_containers=1, to always stay warm.
    scaledown_window=300,
    timeout=600,
)
class LCPModel:
    @modal.enter()
    def load(self):
        """Load the model once per container (paid on cold start only)."""
        os.environ.setdefault("HF_HOME", HF_CACHE_DIR)
        # transformers makes some Hub API calls without forwarding the explicit
        # token (e.g. the tokenizer's mistral-regex check), which 401s on
        # private repos. Exporting HF_TOKEN authenticates those calls too.
        if os.environ.get("LCP_MODEL_TOKEN"):
            os.environ.setdefault("HF_TOKEN", os.environ["LCP_MODEL_TOKEN"])
        from lexetta_lcp.CompLexPerAnnotator.model import load_trained

        # Blank secret values (e.g. an unset token) must become None so
        # load_trained falls back to its defaults instead of passing "".
        self.model, self.tokenizer = load_trained(
            os.environ["LCP_MODEL_DIR"],
            token=os.environ.get("LCP_MODEL_TOKEN") or None,
            revision=os.environ.get("LCP_MODEL_REVISION") or None,
        )
        # load_trained leaves the model on CPU; predict_batch sends inputs to
        # model.device, so moving the model here is all GPU use requires.
        import torch

        if torch.cuda.is_available():
            self.model = self.model.to("cuda")
        hf_cache.commit()

    @modal.method()
    def predict(
        self,
        sentences: list[str],
        tokens: list[str],
        history: list[dict],
    ) -> list[float]:
        """
        Score each (sentence, token) pair against a single shared user history.

        The history is identical for every token in a request, so we send it once
        and fan it out here rather than shipping N copies over the wire.
        """
        from lexetta_lcp.CompLexPerAnnotator.model import predict_batch

        if not tokens:
            return []
        histories = [history] * len(tokens)
        return predict_batch(self.model, self.tokenizer, sentences, tokens, histories)

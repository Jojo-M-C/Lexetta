import { useRef, useState } from "react";
import { Upload } from "lucide-react";
import { api } from "../api";

interface Props {
  onUploaded: () => void;
}

export default function UploadButton({ onUploaded }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClick = () => {
    inputRef.current?.click();
  };

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setError(null);
    setUploading(true);
    try {
      await api.uploadDocument(file);
      onUploaded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div>
      <button
        onClick={handleClick}
        disabled={uploading}
        className="w-full bg-blue-600 hover:bg-blue-700 text-white rounded-lg py-2.5 font-medium flex items-center justify-center gap-2 disabled:bg-gray-300"
      >
        <Upload size={16} />
        {uploading ? "Uploading..." : "Upload File"}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".txt"
        onChange={handleChange}
        className="hidden"
      />
      {error && <p className="text-xs text-red-600 mt-2">{error}</p>}
    </div>
  );
}
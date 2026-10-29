export const RECEIPT_ACCEPT = "image/jpeg,image/jpg,image/png,image/webp,application/pdf,.pdf";
const OK_TYPES = ["image/jpeg", "image/jpg", "image/png", "image/webp", "application/pdf"];
export const RECEIPT_MAX_MB = 10;

// Returns an i18n key for the error, or "" when the file is acceptable.
export function receiptFileError(file) {
  const type = file.type || (/\.pdf$/i.test(file.name) ? "application/pdf" : "");
  if (!OK_TYPES.includes(type)) return "receipt.err.type";
  if (file.size > RECEIPT_MAX_MB * 1024 * 1024) return "receipt.err.size";
  if (file.size === 0) return "receipt.err.empty";
  return "";
}

// Reads a file as data URL, forcing the correct MIME for PDFs with an empty file.type.
export const readReceipt = (file) => new Promise((res, rej) => {
  const r = new FileReader();
  r.onload = () => {
    let url = r.result;
    if (/\.pdf$/i.test(file.name) && url.startsWith("data:application/octet-stream")) url = url.replace("data:application/octet-stream", "data:application/pdf");
    res(url);
  };
  r.onerror = rej;
  r.readAsDataURL(file);
});

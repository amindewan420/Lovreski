# Image Integration Testing Rules

- Always use base64-encoded JPEG/PNG/WEBP images (no SVG/BMP/HEIC/GIF).
- Images must contain real visual features (objects, edges, textures).
- Do not upload blank/uniform images.
- Re-detect MIME after any transcoding.
- Extract first frame only for animated formats.
- Resize oversized images.

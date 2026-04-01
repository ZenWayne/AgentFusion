"""
ocr.py: PDF to markdown via DashScope multimodal OCR.

Converts a PDF to page images, then sends images to the
DashScope multimodal model (qwen-vl-max) for OCR → markdown.

Agent calls this via bash:
  python -m agents.search_agent.ocr <pdf_path> [--output <output_path>]
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def pdf_to_images(pdf_path: str, dpi: int = 150) -> list[str]:
    """
    Convert PDF pages to PNG images using pymupdf (fitz).
    Returns list of temporary image file paths.
    """
    import fitz  # pymupdf

    doc = fitz.open(pdf_path)
    image_paths: list[str] = []
    tmp_dir = tempfile.mkdtemp(prefix="ocr_")

    for page_num, page in enumerate(doc):
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_path = os.path.join(tmp_dir, f"page_{page_num:04d}.png")
        pix.save(img_path)
        image_paths.append(img_path)

    doc.close()
    return image_paths


def _ocr_batch(
    batch_index: int,
    image_paths: list[str],
    model: str,
    prompt: str,
    api_key: str,
) -> tuple[int, str]:
    """OCR a single batch of images. Returns (batch_index, markdown_text)."""
    from dashscope import MultiModalConversation

    content: list[dict] = [{"text": prompt}]
    for img_path in image_paths:
        content.append({"image": f"file://{img_path}"})

    messages = [{"role": "user", "content": content}]

    try:
        response = MultiModalConversation.call(
            model=model,
            messages=messages,
            api_key=api_key,
        )
        if response.status_code == 200:
            choices = response.output.get("choices", [])
            if choices:
                text = choices[0]["message"]["content"]
                if isinstance(text, list):
                    text = " ".join(
                        t["text"] for t in text if isinstance(t, dict) and "text" in t
                    )
                return (batch_index, str(text))
            return (batch_index, f"[OCR batch {batch_index + 1}: no output]")
        return (
            batch_index,
            f"[OCR batch {batch_index + 1} failed: "
            f"status={response.status_code}, message={response.message}]",
        )
    except Exception as e:
        return (batch_index, f"[OCR batch {batch_index + 1} error: {e}]")


def ocr_images_to_markdown(
    image_paths: list[str],
    model: str = "qwen-vl-max",
    task_hint: str = "",
) -> str:
    """
    Send page images to DashScope multimodal model for OCR.

    All batches are submitted in parallel via ThreadPoolExecutor,
    then joined in page order.
    Returns full article markdown text.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        raise EnvironmentError("DASHSCOPE_API_KEY environment variable not set.")

    prompt = (
        "Please perform OCR on the following academic paper pages and convert the content "
        "to well-formatted markdown. Preserve headings, equations (use LaTeX), tables, "
        "and figure captions. Output clean markdown only."
    )
    if task_hint:
        prompt += f"\n\nResearch context: {task_hint}"

    batch_size = 1
    batches = [
        image_paths[i : i + batch_size]
        for i in range(0, len(image_paths), batch_size)
    ]

    results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {
            executor.submit(_ocr_batch, idx, batch, model, prompt, api_key): idx
            for idx, batch in enumerate(batches)
        }
        for future in as_completed(futures, timeout=120):
            idx, text = future.result(timeout=120)
            results[idx] = text

    return "\n\n".join(results[i] for i in range(len(batches)))


def ocr_article(
    pdf_path: str,
    task_hint: str = "",
    model: str = "qwen-vl-max",
    dpi: int = 150,
) -> str:
    """
    Full OCR pipeline: PDF → page images → DashScope OCR → markdown.

    Cleans up temporary image files after OCR.
    Returns full article markdown.
    """
    import shutil

    image_paths = pdf_to_images(pdf_path, dpi=dpi)

    if not image_paths:
        return "[error] No pages extracted from PDF."

    tmp_dir = str(Path(image_paths[0]).parent)

    try:
        markdown = ocr_images_to_markdown(image_paths, model=model, task_hint=task_hint)
    finally:
        if tmp_dir and Path(tmp_dir).exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return markdown


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="OCR a PDF to markdown via DashScope")
    parser.add_argument("pdf_path", help="Path to input PDF file")
    parser.add_argument("--output", default="", help="Output markdown file path (prints to stdout if omitted)")
    parser.add_argument("--task-hint", default="", help="Research task context hint for OCR")
    parser.add_argument("--model", default="qwen-vl-max", help="DashScope model to use")
    parser.add_argument("--dpi", type=int, default=150, help="Image DPI for PDF conversion")
    args = parser.parse_args()

    markdown = ocr_article(args.pdf_path, task_hint=args.task_hint, model=args.model, dpi=args.dpi)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(markdown, encoding="utf-8")
        print(f"OCR output saved to: {args.output}")
    else:
        print(markdown)


if __name__ == "__main__":
    main()

import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist'
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

GlobalWorkerOptions.workerSrc = pdfWorker

export const MAX_PDF_BYTES = 15 * 1024 * 1024
export const MAX_SLIDE_PAGES = 10

export function samplePageNumbers(pageCount, limit = 12) {
  const count = Math.min(pageCount, limit)
  if (count < 1) return []
  if (count === 1) return [1]
  return [...new Set(Array.from({ length: count }, (_, index) =>
    1 + Math.round(index * (pageCount - 1) / (count - 1))))]
}

export function classifySlidePage(width, height, items) {
  const textItems = items.filter((item) => typeof item.str === 'string' && item.str.trim())
  const chars = items.reduce((total, item) => total + (typeof item.str === 'string' ? item.str.length : 0), 0)
  if (textItems.length === 0) return { readable: false, slideLike: false, chars }
  const sizes = textItems.map((item) => Number(item.height) / height)
    .filter((size) => Number.isFinite(size) && size > 0)
    .sort((a, b) => a - b)
  const upperQuartile = sizes[Math.floor((sizes.length - 1) * 0.75)] || 0
  return {
    readable: true,
    slideLike: width / height >= 1.18 && upperQuartile >= 0.026 && chars <= 1600,
    chars,
  }
}

export async function inspectSlideFile(file) {
  if (file.size > MAX_PDF_BYTES) {
    return { kind: 'too_large', pageCount: 0 }
  }
  const data = new Uint8Array(await file.arrayBuffer())
  const loadingTask = getDocument({ data })
  try {
    const pdf = await loadingTask.promise
    const numbers = samplePageNumbers(pdf.numPages)
    let readable = 0
    let slideLike = 0
    for (const number of numbers) {
      const page = await pdf.getPage(number)
      const viewport = page.getViewport({ scale: 1 })
      const content = await page.getTextContent()
      const result = classifySlidePage(viewport.width, viewport.height, content.items)
      readable += Number(result.readable)
      slideLike += Number(result.slideLike)
      page.cleanup()
    }
    const enoughText = readable >= Math.ceil(numbers.length * 0.6)
    const looksLikeSlides = enoughText && slideLike >= Math.ceil(readable * 0.65)
    return {
      kind: !enoughText ? 'unreadable' : looksLikeSlides ? 'slides' : 'document',
      pageCount: pdf.numPages,
      sampledPages: numbers.length,
      readablePages: readable,
      slideLikePages: slideLike,
    }
  } finally {
    await loadingTask.destroy()
  }
}

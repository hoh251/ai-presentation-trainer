import React, { useEffect, useRef, useState } from 'react'
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist'
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

GlobalWorkerOptions.workerSrc = pdfWorker

export default function PdfPreview({ url, pageNumber }) {
  const frameRef = useRef(null)
  const canvasRef = useRef(null)
  const [document, setDocument] = useState(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [status, setStatus] = useState('loading')

  useEffect(() => {
    const frame = frameRef.current
    if (!frame) return
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height })
    })
    observer.observe(frame)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!url) return
    let alive = true
    setDocument(null)
    setStatus('loading')
    const task = getDocument({ url: new URL(url, window.location.href).href })
    task.promise.then((pdf) => {
      if (alive) setDocument(pdf)
      else pdf.destroy()
    }).catch((error) => {
      if (!alive || error?.message?.includes('Loading aborted')) return
      console.error('PDF load failed', error)
      if (alive) setStatus('error')
    })
    return () => {
      alive = false
      task.destroy()
    }
  }, [url])

  useEffect(() => {
    if (!document || !size.width || !size.height) return
    let alive = true
    let renderTask
    setStatus('loading')
    document.getPage(pageNumber).then((page) => {
      if (!alive) return
      const natural = page.getViewport({ scale: 1 })
      const fit = Math.min((size.width - 20) / natural.width, (size.height - 20) / natural.height)
      const viewport = page.getViewport({ scale: Math.max(fit, 0.1) })
      const canvas = canvasRef.current
      if (!canvas) return
      const context = canvas.getContext('2d')
      const ratio = window.devicePixelRatio || 1
      canvas.width = Math.floor(viewport.width * ratio)
      canvas.height = Math.floor(viewport.height * ratio)
      canvas.style.width = `${viewport.width}px`
      canvas.style.height = `${viewport.height}px`
      renderTask = page.render({
        canvasContext: context,
        canvas,
        viewport,
        transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
      })
      return renderTask.promise
    }).then(() => { if (alive) setStatus('ready') }).catch((error) => {
      if (!alive || error?.name === 'RenderingCancelledException') return
      console.error('PDF render failed', error)
      setStatus('error')
    })
    return () => {
      alive = false
      renderTask?.cancel()
    }
  }, [document, pageNumber, size.width, size.height])

  return (
    <div className="pdf-preview" ref={frameRef}>
      <canvas ref={canvasRef} aria-label={`สไลด์หน้า ${pageNumber}`} />
      {status === 'loading' && <div className="pdf-message" role="status"><span>กำลังแสดงสไลด์...</span><div className="loading-track" aria-hidden="true"><div className="loading-fill" /></div></div>}
      {status === 'error' && <div className="pdf-message">แสดง PDF ไม่ได้ กรุณาตรวจไฟล์หรือการเชื่อมต่อ</div>}
    </div>
  )
}

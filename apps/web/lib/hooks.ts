'use client'

import { useEffect, useRef, useState } from 'react'

/** True once the window has scrolled past `threshold` px. */
export function useScrolled(threshold = 12) {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > threshold)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [threshold])

  return scrolled
}

/**
 * Normalised pointer position (-1..1 on both axes) relative to the viewport
 * centre, smoothed via rAF. Drives the hero parallax.
 */
export function usePointerParallax(disabled = false) {
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const frame = useRef<number | null>(null)
  const target = useRef({ x: 0, y: 0 })

  useEffect(() => {
    if (disabled) return
    // Pointer parallax is meaningless without a fine pointer.
    if (!window.matchMedia('(pointer: fine)').matches) return

    const onMove = (e: PointerEvent) => {
      target.current = {
        x: (e.clientX / window.innerWidth) * 2 - 1,
        y: (e.clientY / window.innerHeight) * 2 - 1,
      }
      if (frame.current === null) {
        frame.current = requestAnimationFrame(tick)
      }
    }

    const tick = () => {
      setPos((prev) => {
        const next = {
          x: prev.x + (target.current.x - prev.x) * 0.08,
          y: prev.y + (target.current.y - prev.y) * 0.08,
        }
        const settled =
          Math.abs(next.x - target.current.x) < 0.001 && Math.abs(next.y - target.current.y) < 0.001
        frame.current = settled ? null : requestAnimationFrame(tick)
        return next
      })
    }

    window.addEventListener('pointermove', onMove, { passive: true })
    return () => {
      window.removeEventListener('pointermove', onMove)
      if (frame.current !== null) cancelAnimationFrame(frame.current)
    }
  }, [disabled])

  return pos
}

/** Tracks which of the given section ids is currently in view. */
export function useActiveSection(ids: readonly string[]) {
  const [active, setActive] = useState<string | null>(null)

  useEffect(() => {
    const elements = ids
      .map((id) => document.getElementById(id.replace('#', '')))
      .filter((el): el is HTMLElement => el !== null)

    if (elements.length === 0) return

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
        if (visible) setActive(`#${visible.target.id}`)
      },
      { rootMargin: '-45% 0px -45% 0px', threshold: [0, 0.25, 0.5, 1] },
    )

    elements.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [ids])

  return active
}

/** Fires once when the element enters the viewport. */
export function useInViewOnce<T extends HTMLElement>(amount = 0.4) {
  const ref = useRef<T>(null)
  const [seen, setSeen] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el || seen) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setSeen(true)
          observer.disconnect()
        }
      },
      { threshold: amount },
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [amount, seen])

  return { ref, seen }
}

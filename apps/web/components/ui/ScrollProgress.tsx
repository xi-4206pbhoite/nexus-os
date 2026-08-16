'use client'

import { motion, useScroll, useSpring } from 'framer-motion'

/** A hairline reading-progress bar pinned under the header. */
export function ScrollProgress() {
  const { scrollYProgress } = useScroll()
  const scaleX = useSpring(scrollYProgress, { stiffness: 140, damping: 26, restDelta: 0.001 })

  return (
    <motion.div
      aria-hidden="true"
      style={{ scaleX }}
      className="fixed inset-x-0 top-0 z-[60] h-[3px] origin-left bg-gradient-to-r from-gold-400 via-clay-400 to-steel-500"
    />
  )
}

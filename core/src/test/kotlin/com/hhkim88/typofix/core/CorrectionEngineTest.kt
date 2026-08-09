package com.hhkim88.typofix.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class CorrectionEngineTest {

    @Test
    fun `does not suggest a correction until it has been observed enough times`() {
        val engine = CorrectionEngine(InMemoryCorrectionStore(), minConfidenceCount = 2)

        engine.observeSelfCorrection(TypoCandidate("됬다", "됐다"))
        assertNull(engine.suggestCorrection("됬다")) // only seen once so far

        engine.observeSelfCorrection(TypoCandidate("됬다", "됐다"))
        assertEquals("됐다", engine.suggestCorrection("됬다")) // seen twice now, confident
    }

    @Test
    fun `ignores null or no-op candidates`() {
        val engine = CorrectionEngine(InMemoryCorrectionStore(), minConfidenceCount = 1)
        engine.observeSelfCorrection(null)
        engine.observeSelfCorrection(TypoCandidate("같은말", "같은말"))

        assertEquals(emptyList(), engine.learnedCorrections())
    }

    @Test
    fun `a conflicting correction resets the confidence count instead of flip-flopping`() {
        val engine = CorrectionEngine(InMemoryCorrectionStore(), minConfidenceCount = 2)
        engine.observeSelfCorrection(TypoCandidate("ㅁㄴㅇ", "먼저"))
        engine.observeSelfCorrection(TypoCandidate("ㅁㄴㅇ", "먼저"))
        assertEquals("먼저", engine.suggestCorrection("ㅁㄴㅇ"))

        // user corrects the same typo to something else this time -> confidence resets to 1,
        // so the (now stale) old suggestion stops firing until the new one is confirmed again.
        engine.observeSelfCorrection(TypoCandidate("ㅁㄴㅇ", "먼지"))
        assertNull(engine.suggestCorrection("ㅁㄴㅇ"))

        engine.observeSelfCorrection(TypoCandidate("ㅁㄴㅇ", "먼지"))
        assertEquals("먼지", engine.suggestCorrection("ㅁㄴㅇ"))
    }

    @Test
    fun `disabled corrections are not suggested`() {
        val engine = CorrectionEngine(InMemoryCorrectionStore(), minConfidenceCount = 1)
        engine.observeSelfCorrection(TypoCandidate("염토", "염두"))
        assertEquals("염두", engine.suggestCorrection("염토"))

        engine.setEnabled("염토", false)
        assertNull(engine.suggestCorrection("염토"))
    }

    @Test
    fun `forgetting a correction removes it`() {
        val engine = CorrectionEngine(InMemoryCorrectionStore(), minConfidenceCount = 1)
        engine.observeSelfCorrection(TypoCandidate("ㅇㅇ", "응응"))
        assertEquals(1, engine.learnedCorrections().size)

        engine.forget("ㅇㅇ")
        assertEquals(0, engine.learnedCorrections().size)
    }
}

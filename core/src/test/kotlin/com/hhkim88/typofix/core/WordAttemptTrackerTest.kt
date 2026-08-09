package com.hhkim88.typofix.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class WordAttemptTrackerTest {

    @Test
    fun `detects a typo that was deleted and retyped correctly`() {
        val tracker = WordAttemptTracker()

        tracker.update("됬")
        tracker.update("됬다")   // peak: user typed the (wrong) full word first
        tracker.update("됬")     // starts backspacing
        tracker.update("")
        tracker.update("됐")     // retyping
        tracker.update("됐다")

        val result = tracker.finalizeWord()
        assertEquals(TypoCandidate("됬다", "됐다"), result)
    }

    @Test
    fun `word typed correctly on the first try yields no candidate`() {
        val tracker = WordAttemptTracker()
        tracker.update("안")
        tracker.update("안녕")

        assertNull(tracker.finalizeWord())
    }

    @Test
    fun `mid-word correction that ends back at the same text yields no candidate`() {
        val tracker = WordAttemptTracker()
        tracker.update("가")
        tracker.update("가나")
        tracker.update("가")
        tracker.update("가나") // ended up back at the exact same final word

        assertNull(tracker.finalizeWord())
    }

    @Test
    fun `only the last distinct peak before the final word is used`() {
        val tracker = WordAttemptTracker()
        tracker.update("가")
        tracker.update("가나")   // peak 1: 가나 (abandoned)
        tracker.update("가")
        tracker.update("")
        tracker.update("가")
        tracker.update("가다")   // peak 2: 가다 (abandoned)
        tracker.update("가")
        tracker.update("")
        tracker.update("가")
        tracker.update("가라")   // final

        val result = tracker.finalizeWord()
        assertEquals(TypoCandidate("가다", "가라"), result)
    }

    @Test
    fun `state resets after finalize`() {
        val tracker = WordAttemptTracker()
        tracker.update("가")
        tracker.update("가나")
        tracker.update("가")
        tracker.update("가라")
        tracker.finalizeWord()

        tracker.update("다음")
        assertNull(tracker.finalizeWord())
    }
}

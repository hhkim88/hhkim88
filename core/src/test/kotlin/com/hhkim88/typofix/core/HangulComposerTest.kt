package com.hhkim88.typofix.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class HangulComposerTest {

    private fun HangulComposer.type(jamos: String) {
        for (c in jamos) {
            if (HangulComposer.isConsonant(c)) inputConsonant(c) else inputVowel(c)
        }
    }

    @Test
    fun `simple syllable with final consonant`() {
        val c = HangulComposer()
        c.type("ㄱㅏㄴ")
        assertEquals("간", c.text)
    }

    @Test
    fun `two syllable word with batchim reuse (moving final)`() {
        // ㄱ ㅏ ㄴ ㅏ should split into 가 + 나, not 간 + ㅏ
        val c = HangulComposer()
        c.type("ㄱㅏㄴㅏ")
        assertEquals("가나", c.text)
    }

    @Test
    fun `word requiring vowel and final combination`() {
        // 안녕: ㅇ ㅏ ㄴ ㄴ ㅕ ㅇ
        val c = HangulComposer()
        c.type("ㅇㅏㄴㄴㅕㅇ")
        assertEquals("안녕", c.text)
    }

    @Test
    fun `complex final consonant combination`() {
        // 값: ㄱ ㅏ ㅂ ㅅ (ㅂ+ㅅ -> ㅄ)
        val c = HangulComposer()
        c.type("ㄱㅏㅂㅅ")
        assertEquals("값", c.text)
    }

    @Test
    fun `complex vowel combination`() {
        // 왜: ㅇ ㅗ ㅐ (ㅗ+ㅐ -> ㅙ)
        val c = HangulComposer()
        c.type("ㅇㅗㅐ")
        assertEquals("왜", c.text)
    }

    @Test
    fun `backspace decomposes complex final then vowel then consonant`() {
        val c = HangulComposer()
        c.type("ㄱㅏㅂㅅ")
        assertEquals("값", c.text)

        assertTrue(c.backspace())
        assertEquals("갑", c.text)

        assertTrue(c.backspace())
        assertEquals("가", c.text)

        assertTrue(c.backspace())
        assertEquals("ㄱ", c.text)

        assertTrue(c.backspace())
        assertEquals("", c.text)

        assertFalse(c.backspace())
    }

    @Test
    fun `backspace across settled syllables removes whole syllables`() {
        val c = HangulComposer()
        c.type("ㅇㅏㄴㄴㅕㅇ") // 안녕
        assertEquals("안녕", c.text)

        repeat(3) { c.backspace() } // consume 녕's jong, jung, cho -> back to settled "안"
        assertEquals("안", c.text)

        assertTrue(c.backspace())
        assertEquals("", c.text)
    }

    @Test
    fun `standalone consonant with no vowel is shown as raw jamo`() {
        val c = HangulComposer()
        c.inputConsonant('ㄱ')
        assertEquals("ㄱ", c.text)
    }

    @Test
    fun `reset clears everything`() {
        val c = HangulComposer()
        c.type("ㅇㅏㄴㄴㅕㅇ")
        c.reset()
        assertEquals("", c.text)
        assertTrue(c.isEmpty())
    }
}

package com.hhkim88.typofix.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class DictionarySuggesterTest {

    @Test
    fun `a word already in the dictionary gets no suggestion`() {
        val suggester = DictionarySuggester(WordListDictionary(listOf("안녕", "고마워")))
        assertNull(suggester.suggest("안녕"))
    }

    @Test
    fun `a never-before-seen typo is matched to the one clearly close dictionary word`() {
        val suggester = DictionarySuggester(
            WordListDictionary(listOf("안녕", "반가워", "고마워", "미안해"))
        )
        // "안뇽" was never self-corrected by this user before (no personal learning data at all),
        // but it isn't a real word and sits close to exactly one dictionary entry.
        assertEquals("안녕", suggester.suggest("안뇽"))
    }

    @Test
    fun `ambiguous distance to multiple candidates yields no guess`() {
        // Plain-letter fixtures keep this deterministic: non-Hangul characters always cost
        // exactly 1.0 to substitute (see KeyboardAdjacency), so both candidates tie exactly.
        val suggester = DictionarySuggester(WordListDictionary(listOf("cat", "bat")))
        assertNull(suggester.suggest("hat"))
    }

    @Test
    fun `unambiguous distance picks the clearly nearer candidate`() {
        val suggester = DictionarySuggester(WordListDictionary(listOf("cats", "dogs")))
        assertEquals("cats", suggester.suggest("cars"))
    }

    @Test
    fun `a candidate too far away in any dictionary is not suggested`() {
        val suggester = DictionarySuggester(
            WordListDictionary(listOf("컴퓨터")),
            maxWeightedDistance = 1.0
        )
        assertNull(suggester.suggest("가"))
    }
}

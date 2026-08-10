package com.hhkim88.typofix.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class WeightedEditDistanceTest {

    @Test
    fun `identical sequences have zero distance`() {
        assertEquals(0.0, WeightedEditDistance.compute(listOf('a', 'b', 'c'), listOf('a', 'b', 'c')))
    }

    @Test
    fun `a single deletion costs exactly one`() {
        assertEquals(1.0, WeightedEditDistance.compute(listOf('a', 'b', 'c'), listOf('a', 'b')))
    }

    @Test
    fun `substituting an adjacent key costs less than a distant one`() {
        // ㅐ and ㅔ sit next to each other on the top row; ㅂ and ㅡ are on opposite sides.
        val nearby = KeyboardAdjacency.substitutionCost('ㅐ', 'ㅔ')
        val distant = KeyboardAdjacency.substitutionCost('ㅂ', 'ㅡ')
        assertTrue(nearby < distant)
    }

    @Test
    fun `unknown characters always cost the full substitution price`() {
        assertEquals(1.0, KeyboardAdjacency.substitutionCost('x', 'y'))
    }
}

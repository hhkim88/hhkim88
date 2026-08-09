package com.hhkim88.typofix.ime

/** Key definitions for the standard 두벌식 (2-beolsik) Hangul layout, plus a basic symbols page. */
sealed class Key(val flexWeight: Float = 1f) {
    class Letter(val normal: Char, val shifted: Char = normal, flexWeight: Float = 1f) : Key(flexWeight)
    class Symbol(val char: Char, flexWeight: Float = 1f) : Key(flexWeight)
    object Shift : Key(1.4f)
    object Backspace : Key(1.4f)
    object Space : Key(4f)
    object Enter : Key(1.6f)
    object ToSymbols : Key(1.4f)
    object ToHangul : Key(1.4f)
}

enum class KeyboardMode { HANGUL, SYMBOLS }

object KeyboardLayout {

    val hangulRows: List<List<Key>> = listOf(
        listOf(
            Key.Letter('ㅂ', 'ㅃ'), Key.Letter('ㅈ', 'ㅉ'), Key.Letter('ㄷ', 'ㄸ'),
            Key.Letter('ㄱ', 'ㄲ'), Key.Letter('ㅅ', 'ㅆ'), Key.Letter('ㅛ'),
            Key.Letter('ㅕ'), Key.Letter('ㅑ'), Key.Letter('ㅐ', 'ㅒ'), Key.Letter('ㅔ', 'ㅖ')
        ),
        listOf(
            Key.Letter('ㅁ'), Key.Letter('ㄴ'), Key.Letter('ㅇ'), Key.Letter('ㄹ'), Key.Letter('ㅎ'),
            Key.Letter('ㅗ'), Key.Letter('ㅓ'), Key.Letter('ㅏ'), Key.Letter('ㅣ')
        ),
        listOf(
            Key.Shift,
            Key.Letter('ㅋ'), Key.Letter('ㅌ'), Key.Letter('ㅊ'), Key.Letter('ㅍ'),
            Key.Letter('ㅠ'), Key.Letter('ㅜ'), Key.Letter('ㅡ'),
            Key.Backspace
        ),
        listOf(Key.ToSymbols, Key.Space, Key.Enter)
    )

    val symbolRows: List<List<Key>> = listOf(
        listOf(
            Key.Symbol('1'), Key.Symbol('2'), Key.Symbol('3'), Key.Symbol('4'), Key.Symbol('5'),
            Key.Symbol('6'), Key.Symbol('7'), Key.Symbol('8'), Key.Symbol('9'), Key.Symbol('0')
        ),
        listOf(
            Key.Symbol('-'), Key.Symbol('/'), Key.Symbol(':'), Key.Symbol(';'), Key.Symbol('('),
            Key.Symbol(')'), Key.Symbol('₩'), Key.Symbol('&'), Key.Symbol('@'), Key.Symbol('"')
        ),
        listOf(
            Key.Symbol('.'), Key.Symbol(','), Key.Symbol('?'), Key.Symbol('!'), Key.Symbol('\''),
            Key.Backspace
        ),
        listOf(Key.ToHangul, Key.Space, Key.Enter)
    )
}

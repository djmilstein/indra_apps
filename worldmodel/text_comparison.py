import re

def tokenize_words(s):
    pattern = '[ \./]'
    return re.split(pattern, s)

def words_within_words(text1, text2):
    words1 = tokenize_words(text1)
    words2 = tokenize_words(text2)

    return subsequence_within_subsequence(words1, words2) or \
            subsequence_within_subsequence(words2, words1)

def subsequence_within_subsequence(words1, words2):
    """Checks whether one list is a subsequence of another list.

    Parameters
    ----------
    words1: list<str>
        A list of words
    words2: list<str>
        Another list of words

    Returns
    -------
    within: bool
        Whether the first list of words is within the second list of words
    """
    for match_start in range(len(words2)):
        num_matches = 0
        for i in range(len(words1)):
            if i + match_start < len(words2):
                if words1[i] == words2[i + match_start]:
                    num_matches += 1

        if num_matches == len(words1):
            return True
    return False

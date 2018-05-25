import re

def strip_punctuation(sentence):
    """Removes punctuation in a sentence."""
    punctuations = """.,/\\"';:{}[]()!@#$%^&*"""
    for p in punctuations:
        sentence = sentence.replace(p, '')
    return sentence

def tokenize_words(s):
    pattern = '[ \./]'
    return re.split(pattern, s)

def get_entry_with_common_subsequence(sentence_list, query):
    """Returns a sentence in sentence_list such that it has a common
    subsequence of words with query or vice versa."""

    query_words = tokenize_words(query)
    for sentence in sentence_list:
        sentence_words = tokenize_words(sentence)
        if subsequence_within_subsequence(sentence_words, query_words) or \
                subsequence_within_subsequence(query_words, sentence_words):
                    return sentence
    return None


def words_within_words(sentence1, sentence2):
    """Checks whether either the word sequence in sentence1 is a subsequence of
    the word sequence in sentence2 or vice versa.

    Parameters
    ----------
    sentence1: str
        A sentence, as a string
    sentence2: str
        A sentence, as a string

    Returns
    -------
    within: bool
        Whether either:
        * The word sequence from sentence1 (via word tokenization) is a
            subsequence of the word sequence of sentence 2
        * Vice versa
    num_in_common: int
        The number of words in common, or None if none are in common
    """
    sentence1 = strip_punctuation(sentence1)
    sentence2 = strip_punctuation(sentence2)

    words1 = tokenize_words(sentence1)
    words2 = tokenize_words(sentence2)

    if subsequence_within_subsequence(words1, words2):
        return True, len(words1)
    elif subsequence_within_subsequence(words2, words1):
        return True, len(words2)
    else:
        return False, None

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

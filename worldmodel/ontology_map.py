from text_comparison import words_within_words
from indra.sources.eidos import eidos_api 
from indra.sources.cwms import cwms_api
import collections
import nltk
import pickle

nouns = ['truck',
         'South Sudan',
         'food prices',
         'rainfall',
         'trade',
         'agriculture',
         'government'
        ]

def make_synthetic_sentences(noun):
    sentences = []
    # We create a synthetic sentence with a strucuture that makes it easy
    # for any reader to discern waht the subject and object is. This allows
    # us to cleanly extract the grounding a given reader gives a given noun.
    #
    # CWMS ignores sentences without subject/verb agreement
    # Determining plurality is hard, to include both cases of the verb
    if 'happiness' in noun:
        sentences.append(noun + ' cause sadness.')
        sentences.append(noun + ' causes sadness.')
    else:
        sentences.append(noun + ' cause happiness.')
        sentences.append(noun + ' causes happiness.')
    return ' '.join(sentences)


def get_grounding(reader, noun):
    if reader == 'EIDOS':
        return get_eidos_grounding(noun)
    elif reader == 'CWMS':
        return get_cwms_grounding(noun)
    else:
        assert(False)


def get_eidos_grounding(noun):
    sentence = make_synthetic_sentences(noun)
    ep = eidos_api.process_text(sentence)

    matches = set()
    for statement in ep.statements:
        for agent in statement.agent_list():
            is_match, _ = words_within_words(noun, agent.db_refs['TEXT'])
            if is_match:
                if len(agent.db_refs['EIDOS']) > 0:
                    matches.add(agent.db_refs['EIDOS'][0])
    return matches


def get_cwms_grounding(noun):
    sentence = make_synthetic_sentences(noun)
    print('Test with sentence:', sentence)
    cp = cwms_api.process_text(sentence, None)
    
    matches = set()
    for statement in cp.statements:
        print('Agents for', noun, statement.agent_list())
        for agent in statement.agent_list():
            is_match, _ = words_within_words(noun, agent.db_refs['TEXT'])
            if is_match:
                matches.add(agent.db_refs['CWMS'])
        print('\tResulting matches:', matches)
    return matches


if __name__ == '__main__':
    brown_nouns = set()
    for word, pos in nltk.corpus.brown.tagged_words():
        if pos.startswith('N'):
            brown_nouns.add(word)
    brown_nouns = list(brown_nouns)

    readers = ['EIDOS', 'CWMS']
    matches = collections.defaultdict(dict)
    nn = ['animal', 'dog']
    for noun in nn:  #brown_nouns:
        grounding_eidos = get_grounding('EIDOS', noun)
        grounding_cwms = get_grounding('CWMS', noun)

        if len(grounding_eidos) > 0 and len(grounding_cwms) > 0:
            matches[noun]['EIDOS'] = grounding_eidos
            matches[noun]['CWMS'] = grounding_cwms
    print(matches)
    pickle.dump(matches, open('brown_matches.pkl', 'wb'))

    for match in matches:
        el = list(matches[match]['EIDOS'])
        cl = list(matches[match]['CWMS'])
        print('\t'.join([match, str(el[0]), str(cl[0]) ]))

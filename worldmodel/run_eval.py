from indra.sources import eidos, bbn, cwms, sofia
from indra.util import _require_python3
import os
import glob
import math
import copy
import json
import pickle
import itertools
from nltk import tokenize
from fuzzywuzzy import fuzz, process
from indra.belief import BeliefEngine
import indra.tools.assemble_corpus as ac
from indra.preassembler import Preassembler, render_stmt_graph
from indra.statements import Influence, Concept
from indra.assemblers import CAGAssembler, PysbAssembler
from indra.explanation.model_checker import ModelChecker
from indra.preassembler.hierarchy_manager import HierarchyManager
from indra.sources.eidos.eidos_reader import EidosReader
from text_comparison import words_within_words

# This is a mapping to MITRE's 10 document IDs from our file names
ten_docs_map = {
    '2_IFPRI': '130035 excerpt BG',
    '6_FAO_news': 'CLiMIS_FAO_UNICEF_WFP_SouthSudanIPC_29June_FINAL BG',
    '8_EA_Seasonal Monitor_2017_08_11': 'EA_Seasonal Monitor_2017_08_11 BG',
    '13_SSD_8': 'FAOGIEWSSouthSudanCountryBriefSept2017 BG',
    '15_FEWS NET South Sudan Famine Risk Alert_20170117':
        'FEWS NET South Sudan Famine Risk Alert_20170117 BG',
    '16_South Sudan - Key Message Update_ Thu, 2018-01-25':
        'FEWSNET South Sudan Outlook January 2018 BG',
    '18_FFP Fact Sheet_South Sudan_2018.01.17':
        'FFP Fact Sheet_South Sudan_2018.01.17 BG',
    '52_i8533en': 'i8533en',
    '32_sudantribune':
        'SudanTribune_1_5MillionSSudaneseRiskFacingFamineSaysUN BG',
    '34_Floods displace hundreds in war-torn in South Sudan - '
        'Sudan Tribune_ Plural news and views on Sudan':
        'SudanTribune_FloodsDisplaceHundredsInWar-tornInSouthSudan BG'
    }

def read_eidos(docnames):
    stmts = []
    for docname in docnames:
        fname = os.path.join('docs', '%s.txt' % docname)
        jsonname = os.path.join('eidos', '%s.txt.jsonld' % docname)
        if os.path.exists(jsonname):
            ep = eidos.process_json_ld_file(jsonname)
        else:
            with open(fname, 'r') as fh:
                print('Reading %s' % docname)
                txt = fh.read()
            ep = eidos.process_text(txt, save_json=jsonname,
                                    out_format='json_ld')
        print('%d stmts from %s' % (len(ep.statements), docname))
        # Set the PMID on these statements so that we can get the document ID
        # during assembly
        for stmt in ep.statements:
            stmt.evidence[0].pmid = docname
        stmts += ep.statements
    return stmts


def extract_eidos_text(docnames):
    texts = {}
    # Extract the evidence text for all events into a dict
    for docname in docnames:
        key = docname
        texts[key] = []
        print(docname)
        fname = 'docs/%s.txt' % docname
        with open(fname, 'r') as fh:
            print('Reading %s' % fname)
            txt = fh.read()
        json_fname = 'eidos/%s.txt.jsonld' % docname
        ep = eidos.process_json_ld_file(json_fname)
        for stmt in ep.statements:
            for ev in stmt.evidence:
                texts[key].append(ev.text)
    # Now clean up all the texts to remove redundancies
    for key, sentences in texts.items():
        cleaned_sentences = copy.copy(sentences)
        for s1, s2 in itertools.combinations(sentences, 2):
            if s1 in s2 and s1 in cleaned_sentences:
                cleaned_sentences.remove(s1)
            elif s2 in s1 and s2 in cleaned_sentences:
                cleaned_sentences.remove(s2)
        texts[key] = cleaned_sentences

    return texts


def make_eidos_tsv(statements, fname):
    with open(fname, 'w') as fh:
        for stmt in statements:
            elements = []
            for arg in (stmt.subj, stmt.obj):
                eg = arg.db_refs.get('EIDOS')
                grounding = '' if (not eg or eg[0][1] == 0) else \
                    ('%s/%.2f' % eg[0])
                elements += [arg.name,
                             arg.db_refs['TEXT'],
                             grounding]
            for delta in (stmt.subj_delta, stmt.obj_delta):
                pol = str(delta.get('polarity')) if delta.get('polarity') \
                    else ''
                adjectives = ','.join(delta.get('adjectives', []))
                elements += [pol, adjectives]
            # Add two columns for curation
            elements += ['', '']
            # Now add evidence
            ev = stmt.evidence[0]
            elements += [ev.annotations.get('found_by'),
                         ev.text]
            fh.write('%s\n' % '\t'.join(elements))


def annotate_concept_texts(stmts):
    for stmt in stmts:
        for concept, ann in zip((stmt.subj, stmt.obj),
                                ('subj_text', 'obj_text')):
            txt = concept.name
            stmt.evidence[0].annotations[ann] = txt
        print(stmt.evidence[0].annotations)


def read_bbn(fname, version):
    if version == 'new':
        bp = bbn.process_jsonld_file(fname)
        # Remap doc names
        for stmt in bp.statements:
            stmt.evidence[0].pmid = stmt.evidence[0].pmid[:-4]
    else:
        bp = bbn.process_json_file_old(fname)
    return bp.statements


def read_sofia(fname):
    sp = sofia.process_table(fname, 'Events')
    return sp.statements


def preprocess_cwms(txt):
    # Replace FF character
    txt = txt.replace('\u000c', '\n')
    # Replace parentheses
    txt = txt.replace('-lrb-', '(')
    txt = txt.replace('-LRB-', '(')
    txt = txt.replace('-rrb-', ')')
    txt = txt.replace('-RRB-', ')')
    # Turn into ascii
    txt = txt.encode('ascii', errors='ignore').decode('ascii')
    return txt


def read_cwms_sentences(text_dict, read=True):
    """Read specific sentences with CWMS."""
    bl = 20
    stmts = []
    for doc, sentences in text_dict.items():
        blocks = [sentences[i*bl:i*bl+bl] for i in
                  range(math.ceil(len(sentences)/bl))]
        for j, block in enumerate(blocks):
            block_txt = '.\n'.join(t.capitalize() for t in block)
            block_txt = preprocess_cwms(block_txt)
            if len(blocks) == 1:
                ekb_fname = 'cwms/%s_sentences.ekb' % doc
            else:
                ekb_fname = 'cwms/%s_sentences_%d.ekb' % (doc, j)
            if os.path.exists(ekb_fname):
                with open(ekb_fname, 'r') as fh:
                    cp = cwms.process_ekb(fh.read())
            elif read:
                cp = cwms.process_text(block_txt, save_xml=ekb_fname)
            else:
                continue
            print('%d stmts from %s %d' %
                  (len(cp.statements), ekb_fname, j))
            stmts += cp.statements
            # Set the PMID on these statements so that we can get the document ID
            # during assembly
            for stmt in cp.statements:
                stmt.evidence[0].pmid = doc
    return stmts


def read_cwms_full(fnames, read=True):
    """Read full texts with CWMS."""
    def get_paragraphs(txt):
        # Break up along blank lines
        parts = txt.split('\n\n')
        # Consider a part a paragraph if it's at least 3 lines long
        paras = [p for p in parts if len(p.split('\n')) >=3]
        return paras
    stmts = []
    for fname in fnames:
        basename = '.'.join(fname.split('.')[:-1])
        print(basename)
        with open(fname, 'r') as fh:
            print('Reading %s' % fname)
            txt = fh.read()
        txt = preprocess_cwms(txt)
        # Get paragraphs
        paras = get_paragraphs(txt)
        print('Reading %d paragraphs' % len(paras))
        for i, para in enumerate(paras):
            sentences = tokenize.sent_tokenize(para)
            bl = 20
            blocks = [sentences[i*bl:i*bl+bl] for i in
                      range(math.ceil(len(sentences)/bl))]
            print('Reading %d blocks' % len(blocks))
            for j, block in enumerate(blocks):
                block_txt = ' '.join(block)
                if len(blocks) == 1:
                    ekb_fname = basename + '_%d.ekb' % i
                else:
                    ekb_fname = basename + '_%d_%d.ekb' % (i, j)
                if os.path.exists(ekb_fname):
                    with open(ekb_fname, 'r') as fh:
                        cp = cwms.process_ekb(fh.read())
                elif read:
                    cp = cwms.process_text(block_txt, save_xml=ekb_fname)
                else:
                    continue
                print('%d stmts from %s (%d/%d)' %
                      (len(cp.statements), fname, i, j))
                stmts += cp.statements
    return stmts


def align_entities(stmts_by_ns, match='exact'):
    def get_grounding_map(ns, stmts):
        agents = {}
        for st in stmts:
            for agent in st.agent_list():
                if agent is not None:
                    grounding = agent.db_refs.get(ns)
                    if grounding and ns == 'EIDOS':
                        grounding = grounding[0][0]
                    text = agent.db_refs.get('TEXT')
                    text = text.encode('latin-1', errors='ignore').decode('latin-1')
                    if text and grounding:
                        agents[text] = grounding
        return agents

    def fuzzy_list_match(l1, l2):
        matches = []
        for element1 in l1:
            element2, score = process.extractOne(element1, l2,
                                                 scorer=fuzz.ratio)
            if score > 80:
                matches.append((element1, element2))
        return matches

    grounding_by_ns = {}
    for ns, stmts in stmts_by_ns.items():
        grounding_by_ns[ns] = get_grounding_map(ns, stmts)
    matches = []
    for ns1, ns2 in itertools.combinations(grounding_by_ns.keys(), 2):
        if match == 'exact':
            matches = [(x, x) for x in (set(grounding_by_ns[ns1].keys()) &
                                        set(grounding_by_ns[ns2].keys()))]
        elif match == 'words_within_words':
            for s1, s2 in itertools.product(
                    list(grounding_by_ns[ns1].keys()),
                    list(grounding_by_ns[ns2].keys())):
                print('MOO', s1)

                if words_within_words(s1, s2):
                    t = [s1, s2, ]
                    if len(t) != 2:
                        import ipdb;ipdb.set_trace()
                    assert(len(t) == 2)
                    matches.append(t)
            # matches = list(set(matches))
            print('Point A:', len(matches))

        elif match == 'fuzzy':
            matches = fuzzy_list_match(list(grounding_by_ns[ns1].keys()),
                                       list(grounding_by_ns[ns2].keys()))
        else:
            reader = EidosReader()
            for s1, s2 in itertools.product(
                    list(grounding_by_ns[ns1].keys()),
                    list(grounding_by_ns[ns2].keys())):
                match_score = reader.string_similarity(s1, s2)
                if  match_score > 0.05:
                    matches.append((s1, s2))
            matches = list(set(matches))
        x = 0
        print('Point B:', len(matches))
        matched = []
        for t in matched:
            # print(x, 'Hello', t)
            if len(t) != 2:
                import ipdb;ipdb.set_trace()
            assert len(t) == 2, t
            match1 = t[0]
            match2 = t[1]
            val = (ns1, match1, grounding_by_ns[ns1][match1],
                   ns2, match2, grounding_by_ns[ns2][match2])
            matched.append(val)
            x += 1
    return matched


def dump_alignment(matches, fname):
    with open(fname, 'w') as fh:
        for match in matches:
            row = ','.join(match)
            fh.write('%s\n' % row)


def get_joint_hierarchies():
    eidos_ont = os.path.join(os.path.abspath(eidos.__path__[0]),
                             'eidos_ontology.rdf')
    trips_ont = os.path.join(os.path.abspath(cwms.__path__[0]),
                             'trips_ontology.rdf')
    hm = HierarchyManager(eidos_ont, True, True)
    hm.extend_with(trips_ont)
    hierarchies = {'entity': hm}
    return hierarchies


def run_preassembly(statements, hierarchies):
    print('%d total statements' % len(statements))
    # Filter to grounded only
    statements = ac.filter_grounded_only(statements, score_threshold=0.4)
    # Make a Preassembler with the Eidos and TRIPS ontology
    pa = Preassembler(hierarchies, statements)
    # Make a BeliefEngine and run combine duplicates
    be = BeliefEngine()
    unique_stmts = pa.combine_duplicates()
    print('%d unique statements' % len(unique_stmts))
    be.set_prior_probs(unique_stmts)
    # Run combine related
    related_stmts = pa.combine_related(return_toplevel=False)
    be.set_hierarchy_probs(related_stmts)
    # Filter to top-level Statements
    top_stmts = ac.filter_top_level(related_stmts)
    print('%d top-level statements' % len(top_stmts))
    return top_stmts


def display_delphi(statements):
    from delphi import app
    ca = CAGAssembler(statements)
    cag = ca.make_model()
    cyjs = ca.export_to_cytoscapejs()
    cyjs_str = json.dumps(cyjs)
    app.state.statements = statements
    app.state.CAG = cag
    app.state.elementsJSON = cyjs
    app.state.elementsJSONforJinja = cyjs_str
    app.run()


def get_model_checker(statements):
    pa = PysbAssembler()
    pa.add_statements(statements)
    model = pa.make_model()
    stmt = Influence(Concept('crop_production'), Concept('food_security'))
    mc = ModelChecker(model, [stmt])
    mc.prune_influence_map()
    return mc


def remap_pmids(stmts):
    for stmt in stmts:
        for evidence in stmt.evidence:
            if evidence.pmid in ten_docs_map:
                evidence.pmid = ten_docs_map[evidence.pmid]


def make_mitre_tsv(stmts, fname):
    ca = CAGAssembler(stmts)
    ca.make_model()
    ca.print_tsv(fname)


def plot_assembly(stmts, fname):
    g = render_stmt_graph(stmts, reduce=False, rankdir='TB')
    print(g.nodes())
    g.draw(fname, prog='dot')
    return g

if __name__ == '__main__':
    # Get the IDs of all the documents in the docs folder
    docnames = sorted(['.'.join(os.path.basename(f).split('.')[:-1])
                       for f in glob.glob('docs/*.txt')],
                       key=lambda x: int(x.split('_')[0]))

    # Or rather get just the IDs ot the 10 documents for preliminary analysis
    # docnames = list(ten_docs_map.keys())

    # Gather input from sources
    eidos_stmts = read_eidos(docnames)
    texts = extract_eidos_text(docnames)
    cwms_stmts = read_cwms_sentences(texts, read=False)

    # Read BBN output old and new
    bbn_stmts_new = \
        read_bbn('bbn/bbn_hume_cag_10doc_iteration2_v1/bbn_hume_cat_10doc.json-ld',
                 'new')
    bbn_stmts_old = \
        read_bbn('bbn/bbn-m6-cag.v0.3/cag.json-ld',
                 'old')

    # Read SOFIA output
    sofia_stmts = read_sofia('sofia/SOFIA_output_debugging.xlsx')

    # Align ontologies
    matches_eb = align_entities({'EIDOS': eidos_stmts, 'BBN': bbn_stmts_new},
                                match='words_within_words')
    #dump_alignment(matches_eb, 'EIDOS_BBN_alignment.csv')
    #matches_ec = align_entities({'EIDOS': eidos_stmts, 'CWMS': cwms_stmts},
    #                             match='eidos')
    #dump_alignment(matches_ec, 'EIDOS_CWMS_alignment.csv')
    #matches_bc = align_entities({'BBN': bbn_stmts, 'CWMS': cwms_stmts},
    #                            match='fuzzy')
    #dump_alignment(matches_bc, 'BBN_CWMS_alignment.csv')

    # Collect all statements and assemble
    all_stmts = eidos_stmts + cwms_stmts + bbn_stmts_old + sofia_stmts
    annotate_concept_texts(all_stmts)
    remap_pmids(all_stmts)
    hierarchies = get_joint_hierarchies()
    top_stmts = run_preassembly(all_stmts, hierarchies)
    make_mitre_tsv(top_stmts, 'indra_cag_table.tsv')
    g = plot_assembly(top_stmts, 'indra_cag_assembly.pdf')

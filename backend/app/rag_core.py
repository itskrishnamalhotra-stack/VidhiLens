"""Pure-Python retrieval and evidence helpers for the improved Legal AI RAG pipeline.

The functions in this module are embedded into the Colab notebook.  They have no
model or notebook dependency, so retrieval and deterministic evidence rules can
be regression-tested locally before any GPU time is used.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter


PIPELINE_ID = "multilingual_grounded_rag_2026_09"
MAX_CANDIDATES = 6


def normalise_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    value = value.replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", value).strip()


def tokens(value: str) -> list[str]:
    """Unicode-aware word fragments plus stable Latin morphology stems."""
    value = normalise_text(value)
    raw = re.findall(r"[^\W_]+", value, flags=re.UNICODE)
    result: list[str] = []
    for token in raw:
        result.append(token)
        if token.isascii() and len(token) > 5:
            for suffix in ("ingly", "edly", "ation", "ments", "ment", "ingly", "ing", "ied", "ies", "ed", "es", "s"):
                if token.endswith(suffix) and len(token) - len(suffix) >= 4:
                    result.append(token[:-len(suffix)])
                    break
    return result


def explicit_negative_clauses(value: str) -> str:
    """Remove clearly negated clauses from positive cue matching only."""
    text = normalise_text(value)
    patterns = (
        r"\b(?:no|not|never)\b[^.;!?]*",
        r"\bdo not know\b[^.;!?]*",
        r"\bdon't know\b[^.;!?]*",
        r"\bnot sure\b[^.;!?]*",
        r"\bno facts?\b[^.;!?]*",
        r"\bnahi pata\b[^.;!?]*",
        r"\bkoi (?:fact|jankari|jaankari) nahi\b[^.;!?]*",
        r"\bपता नहीं\b[^।.;!?]*",
        r"\bजानकारी नहीं\b[^।.;!?]*",
    )
    for pattern in patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


# These cues describe statutory concepts, not benchmark cases.  Hindi and
# Hinglish phrases are included because the law catalogue itself is in English.
CONCEPT_PATTERNS: dict[str, tuple[str, ...]] = {
    "BNS_115": (
        r"\b(?:hit|punch|kick|beat|slap|shov|push|assault|bruise|injur|hurt|wound)",
        r"(?:मार|पीट|घूंसा|मुक्का|थप्पड़|धक्का|चोट|घायल)",
    ),
    "BNS_117": (
        r"\b(?:fractur|broken .{0,18}bone|permanent disab|loss of (?:eye|sight|hearing)|disfigur|grievous|severe bodily pain)",
        r"(?:हड्डी.{0,12}टूट|गंभीर चोट|स्थायी विकलांग|आंख.{0,12}खो)",
    ),
    "BNS_303": (
        r"\b(?:stole|stolen|steal|theft|took|taken|removed|carried away|missing (?:phone|laptop|bag|wallet)|without (?:my|the owner's) consent)",
        r"(?:चोर|चोरी|चुरा|सामान.{0,18}ले|फोन.{0,12}नहीं मिल)",
        r"\b(?:churaya|chori|samaan le|phone nahi mil|uthaya.{0,24}le gaya)",
    ),
    "BNS_304": (
        r"\b(?:snatch|grab|yank|wrest|forcibly (?:pull|take|seize)|pulled? .{0,30}(?:hand|neck|shoulder|person))",
        r"(?:छीन|झपट|खींच.{0,20}(?:हाथ|गला|कंधा))",
        r"\b(?:cheena|chheen|jhapta|kheench)",
    ),
    "BNS_316": (
        r"\b(?:entrust|entrusted|repair (?:shop|agent)|rental agent|handed over|gave .{0,30}(?:repair|deliver|keep|return)|sold (?:it|the .{0,18}) and kept|converted|misappropriat|refused to return)",
        r"(?:सौंप|भरोसे|मरम्मत|वापस.{0,18}नहीं|हड़प|बेच.{0,18}पैसे रख)",
        r"\b(?:saunp|bharose|marammat|wapas nahi|hadap)",
    ),
    "BNS_318": (
        r"\b(?:deceiv|fraud|cheat|fabricated .{0,25}(?:certificate|document|record)|false (?:claim|promise|representation|advertisement|document)|paid .{0,45}(?:not deliver|never deliver|blocked)|transferred .{0,35}(?:deposit|payment)|counterfeit|dishonest intention at (?:the )?(?:start|time of payment)|never existed)",
        r"(?:धोख|ठगी|झूठा.{0,18}(?:वादा|दावा|विज्ञापन)|भुगतान.{0,25}(?:डिलीवरी नहीं|ब्लॉक))",
        r"\b(?:dhokha|thagi|fraud intention|delivery delay|seller ne)",
    ),
    "BNS_319": (
        r"\b(?:pretend|impersonat|personat|posed as|fake identity|false identity|claimed to be|as my bank manager|as (?:the )?owner)",
        r"(?:बनकर|होने का नाटक|झूठी पहचान|फर्जी पहचान|प्रतिरूपण|स्वयं को.{0,30}बताकर|खुद को.{0,30}बताकर)",
        r"\b(?:bank manager ban|ban\s?kar|nakli pehchan|farzi pehchan)",
    ),
    "BNS_329": (
        r"\b(?:broke into|break into|enter(?:ed|ing)? .{0,35}(?:home|house|room|warehouse|office|property|storeroom|building)|intruder|trespass|unlawfully remained|stayed inside|locked (?:home|house|room|storeroom))",
        r"(?:घर|मकान|कमरे|गोदाम|दफ्तर).{0,24}(?:घुस|तोड़कर)|अनधिकृत प्रवेश",
        r"\b(?:ghar|makan|kamre|godam).{0,20}(?:ghus|todkar)",
    ),
    "BNS_351": (
        r"\b(?:threat|threaten|blackmail|kill you|harm you|damage .{0,18}(?:house|property)|burn .{0,18}(?:house|home)|withdraw .{0,25}(?:complaint|claim)|unless .{0,35}(?:withdrew|withdraw)|would publish .{0,35}(?:false|damaging)|felt alarmed)",
        r"(?:धमकी|ब्लैकमेल|जान से मार|नुकसान.{0,18}(?:घर|संपत्ति)|शिकायत.{0,18}वापस)",
        r"\b(?:dhamki|jaan se maar|nuksan|complaint wapas)",
    ),
    "BNS_75": (
        r"\b(?:sexual favour|sexual harassment|sexual advance|sexual overture|sex in exchange|demanded sex|sexually coloured remark|explicit sexual remark|sexual remark|(?:show|display)(?:ed|ing)? pornography)",
        r"(?:यौन संबंध|यौन अनुग्रह|अश्लील टिप्पणी|यौन टिप्पणी|चयन.{0,18}बदले.{0,18}यौन)",
        r"\b(?:sexual favour|sex ke badle|ashleel tippani)",
    ),
    "BNS_77": (
        r"\b(?:secretly (?:record|film|watch|photograph)|hidden camera|private (?:act|room|bathroom|image)|changing clothes|captured .{0,20}(?:nude|private|intimate)|disseminat.{0,25}(?:private|intimate) image)",
        r"(?:गुप्त.{0,18}(?:रिकॉर्ड|वीडियो|तस्वीर)|निजी.{0,18}(?:कमरा|कार्य|तस्वीर)|छिपा कैमरा|कपड़े बदल)",
        r"\b(?:chupke|gupt|niji).{0,20}(?:record|video|tasveer)",
    ),
    "BNS_78": (
        r"\b(?:follow(?:ed|ing|s)?|stalk|repeatedly contact|kept contact|wait(?:ed|ing|s)? .{0,30}(?:outside|near) .{0,24}(?:home|house|office|workplace)|despite .{0,25}(?:stop|disinterest|rejected)|monitor(?:ed|ing) .{0,30}(?:email|internet|communication|location))",
        r"(?:पीछा|बार बार.{0,18}(?:संपर्क|मैसेज|फोन)|मना करने.{0,20}(?:बाद|बावजूद)|ईमेल.{0,18}निगरानी)",
        r"\b(?:peecha|picha|baar baar|mana karne ke baad|monitoring)",
    ),
    "ITA_65": (
        r"\b(?:source[- ]code|computer source|program code).{0,60}(?:alter|destroy|conceal|delete|tamper)",
        r"\b(?:alter|destroy|conceal|delete|tamper).{0,60}(?:source[- ]code|computer source|program code)",
        r"(?:सोर्स कोड|स्रोत कोड).{0,40}(?:बदल|नष्ट|छिपा|हटा)",
    ),
    "ITA_66": (
        r"\b(?:hack|hacked|unauthori[sz]ed access|access(?:ed|ing)? .{0,25}(?:account|computer|server|system|email)|logged into .{0,30}(?:server|account|system)|access was revoked|revoked access|copied .{0,30}(?:confidential|customer|data|files)|malware|deleted data|downloaded data without permission|enter(?:ed|ing)? .{0,25}(?:account|system))",
        r"(?:हैक|बिना अनुमति.{0,24}(?:अकाउंट|कंप्यूटर|सिस्टम)|डेटा.{0,18}(?:हटा|डाउनलोड))",
        r"\b(?:hack kiya|bina permission|unauthorised|unauthorized)",
    ),
    "ITA_66B": (
        r"\b(?:received|retained|bought|kept|dealer).{0,45}(?:stolen (?:phone|laptop|computer|device)|knowing .{0,18}stolen)",
        r"\b(?:stolen (?:phone|laptop|computer|device)).{0,45}(?:received|retained|bought|kept|dealer)",
        r"(?:चोरी.{0,24}(?:फोन|मोबाइल|लैपटॉप|कंप्यूटर|डिवाइस).{0,30}(?:खरीद|रखा|प्राप्त|बेच))",
        r"\b(?:chori ka|stolen).{0,28}(?:phone|mobile|tablet|laptop|device).{0,35}(?:liya|rakha|kharida|resale)",
    ),
    "ITA_66C": (
        r"\b(?:used|using|misused|stole|stolen|obtained).{0,40}(?:my |his |her |their )?(?:password|otp|credential|electronic signature|aadhaar|biometric)",
        r"\b(?:password|otp|credential|electronic signature|aadhaar|biometric).{0,35}(?:used|misused|stolen|obtained)",
        r"(?:पासवर्ड|ओटीपी|पहचान|आधार|बायोमेट्रिक|डिजिटल हस्ताक्षर).{0,30}(?:इस्तेमाल|उपयोग|चुरा|दुरुपयोग)",
        r"\b(?:password|otp|credential).{0,25}(?:use kiya|istemal|churaya)",
    ),
    "ITA_66D": (
        r"\b(?:caller|message|online|website|email|account|communication device|computer resource).{0,65}(?:pretend|impersonat|posed as|fake identity|claimed to be)",
        r"\b(?:pretend|impersonat|posed as|fake identity|claimed to be).{0,65}(?:caller|message|online|website|email|account|bank|computer)",
        r"(?:कॉल|मैसेज|ऑनलाइन|ईमेल|अकाउंट).{0,55}(?:बनकर|झूठी पहचान|फर्जी पहचान)",
        r"\b(?:call|message|online|email|whatsapp).{0,55}(?:ban\s?kar|nakli pehchan|farzi pehchan)",
    ),
    "ITA_67": (
        r"\b(?:publish|posted|upload|transmit|sent|shared|circulat).{0,55}(?:obscene|lascivious|prurient|pornographic|porn|indecent (?:image|video|material))",
        r"\b(?:obscene|lascivious|prurient|pornographic|porn|indecent (?:image|video|material)).{0,55}(?:publish|posted|upload|transmit|sent|shared|online)",
        r"(?:अश्लील|पोर्न).{0,35}(?:पोस्ट|अपलोड|भेज|शेयर|प्रसारित)",
        r"\b(?:ashleel|porn).{0,30}(?:post|upload|send|share)",
    ),
    "ITA_67A": (
        r"\b(?:publish|posted|upload|transmit|sent|shared|online).{0,65}(?:sexually explicit|sexual act|having sex|intercourse|explicit video)",
        r"\b(?:sexually explicit|sexual act|having sex|intercourse|explicit video).{0,65}(?:publish|posted|upload|transmit|sent|shared|online)",
        r"(?:यौन क्रिया|यौन संबंध|स्पष्ट यौन|सेक्स वीडियो).{0,40}(?:पोस्ट|अपलोड|भेज|शेयर|प्रसारित)",
        r"\b(?:sex video|sexual act|explicit video).{0,35}(?:post|upload|send|share)",
    ),
}


UNCERTAINTY_PATTERNS: dict[str, tuple[str, ...]] = {
    "BNS_303": (r"\b(?:missing|cannot find|not sure .{0,30}(?:stolen|lost)|don't know .{0,35}(?:stolen|lost))", r"(?:नहीं मिल|पता नहीं.{0,24}(?:चोरी|भूल))", r"\bnahi mil|nahi pata"),
    "BNS_316": (r"\b(?:repair|entrust).{0,80}(?:delay|late|do not know|don't know|no information)", r"(?:मरम्मत|सौंप).{0,55}(?:देरी|जानकारी नहीं)", r"\b(?:repair|marammat).{0,35}(?:delay|late|nahi pata)"),
    "BNS_318": (r"\b(?:delivery|product|seller).{0,70}(?:delay|late|reachable|no facts? .{0,20}dishonest)", r"(?:डिलीवरी|विक्रेता).{0,45}(?:देरी|संपर्क में)", r"\b(?:seller|delivery).{0,45}(?:delay|contact mein|fraud intention ka koi fact nahi)"),
    "BNS_319": (r"\b(?:logo|account|caller).{0,70}(?:do not know|don't know|not know).{0,40}(?:controlled|pretend|identity)", r"(?:लोगो|अकाउंट|कॉलर).{0,55}(?:पता नहीं|झूठी पहचान)",),
    "BNS_351": (r"\b(?:you will regret|vague message|unclear message).{0,60}(?:do not know|don't know|no injury|no harm)", r"(?:पछताओगे|अस्पष्ट संदेश).{0,45}(?:पता नहीं|चोट नहीं)",),
    "BNS_78": (r"\b(?:appeared|saw|seen).{0,35}(?:twice|two times).{0,60}(?:did not contact|don't know .{0,20}follow)", r"(?:दो बार).{0,55}(?:संपर्क नहीं|पता नहीं.{0,15}पीछा)",),
    "ITA_66C": (r"\bpassword.{0,50}(?:stopped working|do not know|don't know).{0,35}(?:used|entered|accessed)",),
    "ITA_66D": (r"\b(?:caller|message|account).{0,65}(?:do not know|don't know|not know).{0,35}(?:impersonat|false identity|pretend)",),
}


RELATED_CANDIDATES: dict[str, tuple[str, ...]] = {
    "BNS_303": ("BNS_304", "BNS_329"),
    "BNS_304": ("BNS_303", "BNS_115"),
    "BNS_316": ("BNS_319",),
    "BNS_318": ("BNS_319", "ITA_66D"),
    "BNS_319": ("BNS_318", "ITA_66D"),
    "BNS_329": ("BNS_303", "BNS_115"),
    "BNS_351": ("ITA_67", "ITA_67A"),
    "BNS_77": ("ITA_67", "ITA_67A"),
    "BNS_78": ("ITA_66",),
    "ITA_66": ("ITA_66C", "ITA_66D"),
    "ITA_66B": ("BNS_318",),
    "ITA_66C": ("ITA_66", "ITA_66D", "BNS_319"),
    "ITA_66D": ("BNS_319", "ITA_66C", "BNS_318"),
    "ITA_67": ("ITA_67A", "BNS_351"),
    "ITA_67A": ("ITA_67", "BNS_77", "BNS_351"),
}


ELEMENT_CHECKLISTS: dict[str, tuple[str, ...]] = {
    "BNS_115": ("A voluntary act caused bodily pain, disease or infirmity.",),
    "BNS_117": ("The injury is grievous, such as fracture, permanent impairment or another stated grievous result.",),
    "BNS_303": ("Movable property was dishonestly moved out of another's possession without consent.",),
    "BNS_304": ("Movable property was suddenly, quickly or forcibly seized, grabbed or taken from a person or possession.",),
    "BNS_316": ("Property was entrusted or placed under dominion.", "The entrusted property was dishonestly converted, used, disposed of or withheld in breach of that trust."),
    "BNS_318": ("There was deception or dishonest concealment.", "The deception induced delivery, retention, action or omission causing likely harm."),
    "BNS_319": ("The person pretended to be another real or imaginary person.", "That personation was used to cheat or induce an act."),
    "BNS_329": ("There was entry onto another's property or unlawful remaining.", "The entry or remaining had intent to commit an offence, intimidate, insult or annoy."),
    "BNS_351": ("There was a threat of injury to person, reputation or property.", "The threat was intended to cause alarm or compel an act or omission."),
    "BNS_75": ("A man made an unwelcome sexual advance, demand, pornography display or sexually coloured remark to a woman.",),
    "BNS_77": ("A woman's private act was watched or captured, or its image was disseminated, without the relevant consent or expectation of observation.",),
    "BNS_78": ("A man repeatedly followed/contacted a woman despite disinterest, or monitored her electronic communication.",),
    "ITA_65": ("Computer source code was knowingly concealed, destroyed or altered.", "The source code was required by law to be kept or maintained."),
    "ITA_66": ("An act covered by IT Act section 43 was done dishonestly or fraudulently, such as unauthorised access, data interference or system damage.",),
    "ITA_66B": ("A stolen computer resource or communication device was received or retained.", "The recipient knew or had reason to believe it was stolen."),
    "ITA_66C": ("Another person's password, electronic signature or unique identification feature was fraudulently or dishonestly used.",),
    "ITA_66D": ("A communication device or computer resource was used.", "Cheating occurred through personation."),
    "ITA_67": ("Material was published or transmitted electronically.", "The material was obscene, lascivious, prurient or likely to deprave or corrupt."),
    "ITA_67A": ("Material containing a sexually explicit act or conduct was published or transmitted electronically.",),
}

DEFAULT_MISSING_QUESTIONS: dict[str, str] = {
    "BNS_115": "What bodily pain or injury was caused, and was it inflicted intentionally or knowingly?",
    "BNS_117": "Did the injury cause a fracture, permanent impairment or another legally grievous result?",
    "BNS_303": "Was movable property dishonestly taken or moved without the possessor's consent?",
    "BNS_304": "Was the property suddenly, quickly or forcibly seized or grabbed from a person or their possession?",
    "BNS_316": "Was entrusted property dishonestly used, sold, converted or withheld in breach of the trust?",
    "BNS_318": "What facts show deception or dishonest intention when the payment, property or action was induced?",
    "BNS_319": "Did the person pretend to be someone else in order to deceive or induce an action?",
    "BNS_329": "Did the person enter or remain on another's property intending an offence, intimidation, insult or annoyance?",
    "BNS_351": "What injury to a person, reputation or property was threatened, and was it meant to cause alarm or compel action?",
    "BNS_75": "Was there an unwelcome sexual advance, demand, pornography display or sexually coloured remark?",
    "BNS_77": "Was a woman's private act watched, captured or disseminated without the relevant consent or expectation of observation?",
    "BNS_78": "Was a woman repeatedly followed or contacted despite disinterest, or was her electronic communication monitored?",
    "ITA_65": "Was legally maintained computer source code knowingly concealed, destroyed or altered?",
    "ITA_66": "Was a computer-related act such as unauthorised access or data interference done dishonestly or fraudulently?",
    "ITA_66B": "Did the recipient know or have reason to believe the computer resource or device was stolen?",
    "ITA_66C": "Did another person fraudulently or dishonestly use the victim's password, signature or unique identification feature?",
    "ITA_66D": "Was a communication device or computer resource used to cheat by pretending to be another person?",
    "ITA_67": "Was obscene or lascivious material published or transmitted electronically?",
    "ITA_67A": "Was material containing a sexually explicit act or conduct published or transmitted electronically?",
}


def _hits(text: str, patterns: tuple[str, ...]) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE)]


def build_retriever(catalogue_rows: list[dict]) -> dict:
    approved = [
        row for row in catalogue_rows
        if row.get("recommendable") and row.get("legal_status") == "in_force"
        and row.get("provision_kind") == "offence"
    ]
    by_id = {row["provision_id"]: row for row in catalogue_rows}
    approved_ids = {row["provision_id"] for row in approved}
    if approved_ids != set(CONCEPT_PATTERNS):
        raise ValueError(
            "Approved catalogue and concept profiles differ: "
            f"missing_profiles={sorted(approved_ids - set(CONCEPT_PATTERNS))}, "
            f"stale_profiles={sorted(set(CONCEPT_PATTERNS) - approved_ids)}"
        )
    docs = []
    titles = []
    for row in approved:
        title = row.get("title", "")
        titles.append(set(tokens(title)))
        docs.append(tokens((title + " ") * 4 + row.get("verified_text", "")))
    df = Counter()
    for document in docs:
        df.update(set(document))
    return {
        "rows": approved,
        "by_id": by_id,
        "index": {row["provision_id"]: index for index, row in enumerate(approved)},
        "docs": docs,
        "titles": titles,
        "df": df,
        "average_length": sum(map(len, docs)) / len(docs),
    }


def _bm25_scores(complaint: str, retriever: dict) -> dict[str, float]:
    query = Counter(tokens(explicit_negative_clauses(complaint)))
    count = len(retriever["docs"])
    scores: dict[str, float] = {}
    for index, document in enumerate(retriever["docs"]):
        frequencies = Counter(document)
        length = len(document)
        score = 0.0
        for term, query_frequency in query.items():
            term_frequency = frequencies.get(term, 0)
            if not term_frequency:
                continue
            document_frequency = retriever["df"].get(term, 0)
            idf = math.log(1 + (count - document_frequency + 0.5) / (document_frequency + 0.5))
            denominator = term_frequency + 1.4 * (1 - 0.72 + 0.72 * length / retriever["average_length"])
            score += idf * (term_frequency * 2.4 / denominator) * min(query_frequency, 2)
            if term in retriever["titles"][index]:
                score += 1.4 * idf
        scores[retriever["rows"][index]["provision_id"]] = score
    return scores


def triage_seed_ids(triage: object) -> list[str]:
    if not isinstance(triage, dict):
        return []
    result = [item for item in triage.get("possible_provision_ids", []) if isinstance(item, str)]
    for item in triage.get("uncertain_sections", []):
        if isinstance(item, dict) and isinstance(item.get("provision_id"), str):
            result.append(item["provision_id"])
    return list(dict.fromkeys(result))


def retrieve_candidates(complaint: str, triage: object, retriever: dict,
                        max_candidates: int = MAX_CANDIDATES) -> dict:
    full_text = normalise_text(complaint)
    positive_text = explicit_negative_clauses(complaint)
    bm25 = _bm25_scores(complaint, retriever)
    seeds = [item for item in triage_seed_ids(triage) if item in retriever["index"]]
    strong_hits: dict[str, list[str]] = {}
    uncertain_hits: dict[str, list[str]] = {}
    scores: dict[str, float] = {}
    for provision_id in retriever["index"]:
        strong = _hits(positive_text, CONCEPT_PATTERNS[provision_id])
        uncertain = _hits(full_text, UNCERTAINTY_PATTERNS.get(provision_id, ()))
        strong_hits[provision_id] = strong
        uncertain_hits[provision_id] = uncertain
        score = bm25.get(provision_id, 0.0)
        score += 52.0 * min(len(strong), 2)
        score += 38.0 * min(len(uncertain), 1)
        if provision_id in seeds:
            score += 32.0
        scores[provision_id] = score

    primary = {
        provision_id for provision_id in retriever["index"]
        if strong_hits[provision_id] or uncertain_hits[provision_id] or provision_id in seeds
    }
    companion_bonus: Counter[str] = Counter()
    for provision_id in primary:
        for related in RELATED_CANDIDATES.get(provision_id, ()):
            if related in retriever["index"]:
                companion_bonus[related] += 1
    for provision_id, count in companion_bonus.items():
        # A companion is a candidate for legal comparison.  It never becomes a
        # final answer without passing the model assessment and evidence gate.
        scores[provision_id] += min(count, 2) * 12.0

    ordered_ids = sorted(
        retriever["index"],
        key=lambda provision_id: (
            -(provision_id in primary),
            -scores[provision_id],
            provision_id,
        ),
    )
    # If neither the text nor LoRA produces any scoped signal, remain out of
    # scope.  Otherwise include the best companions up to the fixed budget.
    if not primary:
        ordered_ids = []
    else:
        ordered_ids = ordered_ids[:max_candidates]

    candidates = []
    for provision_id in ordered_ids:
        row = retriever["by_id"][provision_id]
        candidates.append({
            "provision_id": provision_id,
            "title": row.get("title"),
            "verified_text": row.get("verified_text", ""),
            "legal_status": row.get("legal_status"),
            "provision_kind": row.get("provision_kind"),
            "recommendable": bool(row.get("recommendable")),
            "retrieval_score": round(scores[provision_id], 6),
            "concept_hit_count": len(strong_hits[provision_id]),
            "uncertainty_hit_count": len(uncertain_hits[provision_id]),
            "triage_seed": provision_id in seeds,
            "companion_candidate": bool(companion_bonus[provision_id]) and provision_id not in primary,
            "element_checklist": list(ELEMENT_CHECKLISTS[provision_id]),
        })

    context_ids: list[str] = []
    if "ITA_66" in ordered_ids and "ITA_43" in retriever["by_id"]:
        context_ids.append("ITA_43")
    context = []
    for provision_id in context_ids:
        row = retriever["by_id"][provision_id]
        context.append({
            "provision_id": provision_id,
            "title": row.get("title"),
            "verified_text": row.get("verified_text", ""),
            "legal_status": row.get("legal_status"),
            "provision_kind": row.get("provision_kind"),
            "recommendable": bool(row.get("recommendable")),
        })
    return {
        "offence_candidates": candidates,
        "context_candidates": context,
        "retrieval_method": PIPELINE_ID,
    }


def cue_state(complaint: str, provision_id: str) -> dict:
    full_text = normalise_text(complaint)
    positive_text = explicit_negative_clauses(complaint)
    return {
        "positive": bool(_hits(positive_text, CONCEPT_PATTERNS[provision_id])),
        "uncertain": bool(_hits(full_text, UNCERTAINTY_PATTERNS.get(provision_id, ()))),
    }


def strong_grounded_ids(complaint: str, candidate_ids: list[str] | set[str]) -> set[str]:
    """Return candidates whose distinguishing facts are explicit in the complaint.

    These patterns are deliberately stricter than retrieval cues. They are used
    only to recover a section that the model left as a question, never to expand
    beyond provisions already retrieved from the verified catalogue.
    """
    text = normalise_text(complaint)
    positive = explicit_negative_clauses(complaint)
    candidates = set(candidate_ids)
    result: set[str] = set()

    def has(pattern: str, value: str = positive) -> bool:
        return bool(re.search(pattern, value, flags=re.IGNORECASE))

    physical_hurt = has(
        r"\b(?:hit|punch(?:ed)?|kick(?:ed)?|beat|slap(?:ped)?|injur(?:ed|y)|bruise(?:d)?)\b"
        r"|(?:मारा|पीटा|घूंसा|मुक्का|थप्पड़|चोट|घायल)"
    )
    if "BNS_115" in candidates and physical_hurt:
        result.add("BNS_115")

    deception = has(r"\b(?:deceiv\w*|cheat\w*|trick\w*|fake (?:scheme|plan)|dishonest intention)\b|(?:धोख|ठगी|फर्जी योजना)")
    induced_action = has(
        r"\b(?:paid|payment|money|deposit|transfer(?:red)?|invest(?:ed|ment)?|documents?|property)\b"
        r"|(?:पैसे|राशि|भुगतान|निवेश|दस्तावेज|संपत्ति|(?:पैसे|राशि).{0,12}जमा)"
    )
    if "BNS_318" in candidates and deception and induced_action:
        result.add("BNS_318")

    personation = has(
        r"\b(?:impersonat\w*|pretend(?:ed|ing)? to be|posed as|claimed to be|fake identity|as (?:the )?owner)\b"
        r"|(?:बनकर|स्वयं को.{0,30}बताकर|खुद को.{0,30}बताकर|झूठी पहचान|फर्जी पहचान)"
        r"|\b(?:ban\s?kar|bankar|nakli pehchan|farzi pehchan)\b"
    )
    if "BNS_319" in candidates and personation:
        result.add("BNS_319")

    property_entry = has(
        r"\b(?:broke into|break into|trespass|entered .{0,35}(?:house|home|warehouse|office|property|room).{0,35}without permission)"
        r"|(?:घर|मकान|गोदाम|दफ्तर|कमरे).{0,24}(?:घुस|तोड़कर)"
    )
    if "BNS_329" in candidates and property_entry:
        result.add("BNS_329")

    concrete_threat = has(
        r"\b(?:threaten(?:ed)?|blackmail(?:ed)?|kill you|burn .{0,25}(?:car|house|home)|terminate .{0,20}(?:job|employment)|harm .{0,20}(?:you|family|property)|unless .{0,45})"
        r"|(?:धमकी|ब्लैकमेल|जान से मार|नौकरी.{0,18}निकाल|संपत्ति.{0,18}नुकसान)"
    )
    if "BNS_351" in candidates and concrete_threat:
        result.add("BNS_351")

    pursuit = has(r"\b(?:follow(?:ed|ing|s)?|stalk(?:ed|ing)?|monitor(?:ed|ing))\b|(?:पीछा|निगरानी)")
    persistence = has(
        r"\b(?:after (?:i|she) rejected|despite .{0,25}(?:stop|disinterest)|continue(?:d)?|repeatedly|several days)\b"
        r"|(?:मना करने.{0,20}(?:बाद|बावजूद)|बार बार|लगातार)"
    )
    if "BNS_78" in candidates and pursuit and persistence:
        result.add("BNS_78")

    computer_access = has(
        r"\b(?:hack(?:ed|ing)?|unauthori[sz]ed access|enter(?:ed|ing)? .{0,30}(?:account|email|server|system)|access(?:ed|ing)? .{0,30}(?:account|email|server|system)|intruder .{0,25}(?:account|email|server|system))"
        r"|(?:हैक|बिना अनुमति.{0,24}(?:अकाउंट|खाते|कंप्यूटर|सिस्टम|सर्वर)|खाते में प्रवेश)"
    )
    wrongful_access = has(
        r"\b(?:fraud\w*|dishonest|hack(?:ed|ing)?|intruder|without (?:permission|authorisation|authorization)|illegally|stolen .{0,20}password|intentionally .{0,25}(?:altered|deleted|downloaded))"
        r"|(?:धोख|बेईमान|बिना अनुमति|अवैध|जानबूझकर)"
    )
    if "ITA_66" in candidates and computer_access and wrongful_access:
        result.add("ITA_66")

    stolen_device = has(
        r"\b(?:stolen|theft|chori)\b.{0,30}\b(?:phone|mobile|tablet|laptop|computer|device)\b"
        r"|(?:चोरी).{0,30}(?:फोन|मोबाइल|टैबलेट|लैपटॉप|कंप्यूटर|डिवाइस)"
    )
    receipt = has(
        r"\b(?:received|retained|bought|dealer|kept .{0,20}(?:for resale|with him)|liya|rakha|kharida)\b"
        r"|(?:प्राप्त|खरीद|अपने पास रखा|बेचने के लिए)"
    )
    knowledge = has(r"\b(?:knowing|knowingly|knew|after being shown|jaante hue)\b|(?:जानते हुए|पता होने के बाद)")
    if "ITA_66B" in candidates and stolen_device and receipt and knowledge:
        result.add("ITA_66B")

    credential_use = has(
        r"\b(?:used|using|misused).{0,35}(?:password|otp|credential|electronic signature|digital signature|aadhaar|biometric)"
        r"|\b(?:password|otp|credential|electronic signature|digital signature|aadhaar|biometric).{0,35}(?:used|misused)"
        r"|\b(?:password|otp|credential).{0,35}(?:use karke|use kiya|istemal|istamaal)"
        r"|(?:पासवर्ड|ओटीपी|आधार|बायोमेट्रिक|डिजिटल हस्ताक्षर).{0,30}(?:इस्तेमाल|उपयोग|दुरुपयोग)"
    )
    digital_identity_profile = has(
        r"\b(?:created|made|opened).{0,25}(?:fake )?(?:profile|account).{0,25}in my name\b"
        r"|\b(?:fake profile|fake account).{0,25}(?:in my name|using my identity)\b"
    ) and personation
    if "ITA_66C" in candidates and (credential_use or digital_identity_profile):
        result.add("ITA_66C")

    return result


def apply_output_cleaner(complaint: str, supported_ids: list[str],
                         missing_questions: dict[str, str],
                         candidate_ids: list[str]) -> tuple[list[str], dict[str, str], list[dict]]:
    """Promote explicit multi-offence facts and remove redundant alternatives."""
    text = normalise_text(complaint)
    positive = explicit_negative_clauses(complaint)
    kept = list(dict.fromkeys(supported_ids))
    questions = dict(missing_questions)
    actions: list[dict] = []
    strong = strong_grounded_ids(complaint, candidate_ids)

    for provision_id in candidate_ids:
        if provision_id in strong and provision_id not in kept:
            kept.append(provision_id)
            actions.append({"provision_id": provision_id, "action": "promoted_from_explicit_facts"})

    # Identity theft requires actual use of a password, signature or another
    # unique identification feature. Account entry alone belongs under ITA_66.
    if "ITA_66C" in kept and "ITA_66C" not in strong:
        kept.remove("ITA_66C")
        actions.append({"provision_id": "ITA_66C", "action": "removed_without_credential_use"})

    # Cheating by personation needs an express pretence of being somebody else.
    if "BNS_319" in kept and "BNS_319" not in strong:
        kept.remove("BNS_319")
        actions.append({"provision_id": "BNS_319", "action": "removed_without_personation"})

    # Receiving a stolen device is distinct from being the person who took it.
    receipt_context = bool(re.search(
        r"\b(?:dealer|received|retained|bought|for resale|liya|rakha|kharida)\b"
        r"|(?:दुकानदार|प्राप्त|खरीद|अपने पास रखा|बेचने के लिए)", text, flags=re.IGNORECASE))
    active_taking = bool(re.search(
        r"\b(?:stole|took|removed|snatched|carried away|churaya)\b|(?:चुराया|छीन|उठाकर.{0,15}ले गया)",
        positive, flags=re.IGNORECASE))
    if "ITA_66B" in kept and "BNS_303" in kept and receipt_context and not active_taking:
        kept.remove("BNS_303")
        actions.append({"provision_id": "BNS_303", "action": "removed_receiver_not_taker"})

    kept, questions, gate_actions = apply_deterministic_gates(complaint, kept, questions)
    actions.extend(gate_actions)
    kept_set = set(kept)

    def suppress(provision_id: str, reason: str) -> None:
        if provision_id in questions and provision_id not in kept_set:
            questions.pop(provision_id, None)
            actions.append({"provision_id": provision_id, "action": "question_suppressed", "reason": reason})

    if "BNS_303" in kept_set and "BNS_304" not in strong:
        suppress("BNS_304", "The facts describe theft without sudden or forcible taking from a person.")
    if kept_set & {"BNS_304", "BNS_316", "ITA_66B"}:
        suppress("BNS_303", "A more specific taking, entrustment or stolen-device receipt provision is supported.")
    if "BNS_117" in kept_set:
        suppress("BNS_115", "The same injury is already described by the grievous-hurt provision.")
    if kept_set & {"BNS_319", "ITA_66D"}:
        suppress("BNS_318", "The same deception is already described as personation.")
    if "ITA_67A" in kept_set:
        suppress("ITA_67", "The electronically transmitted material is already described by the specific sexually-explicit provision.")
    if "BNS_75" in kept_set and "BNS_78" not in strong:
        suppress("BNS_78", "No repeated following, contact or communication monitoring is stated.")
    if "BNS_77" in kept_set and not re.search(
            r"\b(?:publish|posted|upload|transmit|sent|shared|circulat)\b|(?:पोस्ट|अपलोड|भेज|शेयर|प्रसारित)",
            positive, flags=re.IGNORECASE):
        suppress("ITA_67", "No electronic publication or transmission is stated.")
        suppress("ITA_67A", "No electronic publication or transmission is stated.")
    if "ITA_66" not in strong:
        suppress("ITA_66", "No explicit dishonest or fraudulent computer access is stated.")
    if "ITA_66C" not in strong:
        suppress("ITA_66C", "No actual use of another person's identifying credential is stated.")
    if "BNS_318" not in strong and kept_set:
        suppress("BNS_318", "No separate inducement by deception is stated.")

    questions = {key: value for key, value in questions.items() if key not in kept_set}
    return kept, questions, actions


def explicit_transaction_uncertainty(complaint: str) -> bool:
    """Detect a paid seller transaction that expressly lacks dishonest-intent facts."""
    text = normalise_text(complaint)
    transaction = bool(re.search(
        r"\b(?:seller|product|delivery|paid|payment)\b|(?:विक्रेता|सामान|डिलीवरी|भुगतान|seller)",
        text, flags=re.IGNORECASE))
    missing_intent = bool(re.search(
        r"\b(?:no facts? .{0,35}dishonest intention|fraud intention .{0,20}(?:no fact|nahi)|do not know .{0,35}dishonest)"
        r"|(?:धोखाधड़ी की नीयत.{0,25}(?:पता नहीं|जानकारी नहीं))",
        text, flags=re.IGNORECASE))
    return transaction and missing_intent


def has_scoped_legal_subject(complaint: str) -> bool:
    """Whether an otherwise empty triage still identifies a covered subject."""
    text = explicit_negative_clauses(complaint)
    return bool(re.search(
        r"\b(?:password|credential|otp|signature|account|property|phone|wallet|injury|threat|payment|seller|stolen|missing)\b"
        r"|(?:पासवर्ड|ओटीपी|हस्ताक्षर|खाता|संपत्ति|फोन|चोट|धमकी|भुगतान|चोरी)",
        text, flags=re.IGNORECASE))


def apply_deterministic_gates(complaint: str, supported_ids: list[str],
                              missing_questions: dict[str, str]) -> tuple[list[str], dict[str, str], list[dict]]:
    """Apply small, general statutory distinctions after model assessment."""
    text = normalise_text(complaint)
    kept = list(dict.fromkeys(supported_ids))
    kept_set = set(kept)
    questions = dict(missing_questions)
    actions: list[dict] = []

    def remove(provision_id: str, reason: str, question: str | None = None) -> None:
        if provision_id not in kept_set:
            return
        kept_set.remove(provision_id)
        actions.append({"provision_id": provision_id, "action": "removed", "reason": reason})
        if question:
            questions.setdefault(provision_id, question)

    # Specific provisions replace their general counterpart when both refer to
    # the same conduct in the complaint.
    if "BNS_117" in kept_set:
        remove("BNS_115", "The same injury is described as grievous, so the grievous-hurt provision is the specific candidate.")
    if "BNS_304" in kept_set:
        remove("BNS_303", "The same taking is described as sudden, quick or forcible snatching.")
    if "BNS_319" in kept_set:
        remove("BNS_318", "The same deception is specifically described as cheating by personation.")
    if "ITA_67A" in kept_set:
        remove("ITA_67", "The same electronic material is specifically described as containing a sexually explicit act.")

    entrustment = bool(re.search(r"\bentrust|repair|rental agent|handed over\b|(?:सौंप|मरम्मत|भरोसे)", text))
    converted = bool(re.search(r"\bsold|kept the (?:money|proceeds)|converted|pawned|disposed|refused to return\b|(?:बेच|हड़प|वापस नहीं)", text))
    if "BNS_316" in kept_set and entrustment and converted:
        remove("BNS_303", "The property was voluntarily entrusted before the stated conversion or disposal.")

    # Do not treat movement of account balances or credentials as physical
    # theft without a separate movable-property taking.
    physical_property = bool(re.search(
        r"\b(?:phone|laptop|bag|wallet|camera|television|equipment|jewellery|cash|vehicle|property|device)\b|(?:फोन|लैपटॉप|बैग|कैमरा|सामान)",
        text,
    ))
    only_account_transfer = bool(re.search(r"\b(?:bank|account|transfer|otp|password|credential)\b", text)) and not physical_property
    if only_account_transfer:
        remove("BNS_303", "The complaint states account or credential misuse without a separate taking of movable property.")

    # A mere contractual delay does not itself establish dishonest conversion or
    # deception. Preserve a targeted question instead of a positive section.
    delay_without_dishonesty = bool(re.search(
        r"\b(?:delay|late|reachable|contact mein|investigat)|(?:देरी|संपर्क में)\b", text
    )) and bool(re.search(
        r"\b(?:do not know|don't know|no facts?|no information|nahi pata|koi fact nahi)|(?:पता नहीं|जानकारी नहीं)\b", text
    ))
    if delay_without_dishonesty:
        remove("BNS_316", "Delay alone does not establish dishonest conversion of entrusted property.",
               "Was the entrusted property dishonestly used, sold, converted or refused rather than merely delayed?")
        remove("BNS_318", "Delay alone does not establish deception or dishonest intention when payment was taken.",
               "What facts show that the seller intended to deceive you when accepting payment?")

    # Retain original order.
    kept = [item for item in kept if item in kept_set]
    return kept, questions, actions

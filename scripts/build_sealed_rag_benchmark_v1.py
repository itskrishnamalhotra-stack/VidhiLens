"""Build the independent 150-case RAG benchmark and verify training separation."""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path


ROOT = Path(r"E:\term paper project")
PHASE1 = ROOT / "phase1"
OUTPUT = PHASE1 / "evaluation/sealed_rag_benchmark_v1"
TRAINING_ZIP = PHASE1 / "exports/colab_training_input_v5.zip"
OLD_MANUAL_RESULTS = PHASE1 / "exports/rag_v2_1_comparison_results.json"
RECOMMENDABLE = {
    "BNS_75", "BNS_77", "BNS_78", "BNS_115", "BNS_117", "BNS_303",
    "BNS_304", "BNS_316", "BNS_318", "BNS_319", "BNS_329", "BNS_351",
    "ITA_65", "ITA_66", "ITA_66B", "ITA_66C", "ITA_66D", "ITA_67", "ITA_67A",
}

cases: list[dict] = []


def add(group: str, complaint: str, outcome: str, required=(), optional=(),
        uncertain=(), forbidden=(), language="en", difficulty="standard", rationale="") -> None:
    case_id = f"SRB1_{len(cases) + 1:03d}"
    required = list(required)
    optional = list(optional)
    uncertain = list(uncertain)
    forbidden = list(forbidden)
    if outcome == "provision_match" and not required:
        raise ValueError(f"{case_id}: provision_match requires a section")
    if outcome != "provision_match" and required:
        raise ValueError(f"{case_id}: non-match cannot have required sections")
    for provision_id in required + optional + uncertain + forbidden:
        if provision_id not in RECOMMENDABLE:
            raise ValueError(f"{case_id}: unsupported gold id {provision_id}")
    cases.append({
        "case_id": case_id,
        "group": group,
        "language": language,
        "difficulty": difficulty,
        "complaint": complaint.strip(),
        "gold": {
            "outcome": outcome,
            "required_provision_ids": required,
            "optional_provision_ids": optional,
            "required_uncertain_ids": uncertain,
            "forbidden_provision_ids": forbidden,
            "rationale": rationale.strip(),
        },
    })


SINGLE = {
    "BNS_75": [
        "At a client meeting, my supervisor repeatedly demanded a sexual favour in exchange for approving my leave. I refused and preserved his messages.",
        "A male colleague deliberately displayed pornography to me on his phone after I told him I did not want to see it. Two employees witnessed this.",
        "Office mein manager baar-baar mere body par sexually coloured remarks karta hai aur mana karne ke baad bhi sexual favour maangta hai.",
        "एक पुरुष प्रशिक्षक ने महिला खिलाड़ी से चयन के बदले यौन संबंध की मांग की। उसने साफ मना किया और बातचीत रिकॉर्ड है।",
    ],
    "BNS_77": [
        "A man hid a camera inside the women's changing cubicle and recorded me while I was undressing. I had no knowledge of or consent to the recording.",
        "I consented to my partner taking a private photograph of me in underwear, but he later sent that image to his friends without my consent.",
        "Ek aadmi ne ladies washroom ke andar chupkar mera video banaya jab main privacy expect kar rahi thi. Maine recording ki permission nahi di thi.",
        "एक व्यक्ति ने महिला के निजी कमरे में कपड़े बदलते समय उसकी तस्वीर चुपके से ली और बाद में उसे साझा किया।",
    ],
    "BNS_78": [
        "After I repeatedly asked a man to stop contacting me, he followed me from college to my home on four days and waited outside the gate.",
        "A man keeps monitoring my email and social-media activity and sends messages describing where I was online, despite my clear request that he stop.",
        "Maine use kai baar contact band karne ko kaha, phir bhi woh roz office tak follow karta hai aur ghar ke bahar wait karta hai.",
        "मेरे मना करने के बाद भी एक पुरुष लगातार मेरा पीछा करता है और मेरी ऑनलाइन गतिविधि पर नजर रखता है।",
    ],
    "BNS_115": [
        "During a quarrel, my neighbour intentionally punched my shoulder, causing pain and bruising. The clinic found no fracture or lasting injury.",
        "A customer knowingly pushed me down to hurt me. I suffered a painful cut that required cleaning but no stitches or fracture.",
        "Usne jaanbujhkar mujhe thappad mara, jis se dard aur halka swelling hua, lekin koi fracture nahi tha.",
        "बहस में उसने जानबूझकर मुझे धक्का देकर गिराया, जिससे दर्द और साधारण चोट आई लेकिन कोई गंभीर चोट नहीं हुई।",
    ],
    "BNS_117": [
        "A man deliberately struck my face with a heavy object and the medical report confirms permanent disfigurement of my cheek.",
        "My attacker intentionally hit my leg with a metal bar. The X-ray confirms that the tibia was fractured.",
        "Hamle mein usne jaanbujhkar meri aankh par vaar kiya aur doctor ne permanent loss of vision confirm kiya.",
        "आरोपी ने जानबूझकर मेरे हाथ पर वार किया और एक्स-रे में हड्डी टूटने की पुष्टि हुई।",
    ],
    "BNS_303": [
        "While I was asleep in a waiting room, someone quietly removed my wallet from the bag beside me without my consent.",
        "CCTV shows a visitor taking my bicycle from the locked office parking area and riding away without permission.",
        "Kisi ne meri table se phone bina permission uthaya aur chupke se le gaya. CCTV mein poora act record hai.",
        "एक व्यक्ति ने दुकान के काउंटर से मेरा बटुआ बिना अनुमति उठाया और उसे लेकर चला गया।",
    ],
    "BNS_304": [
        "A rider suddenly grabbed the chain from my neck and sped away before I could react.",
        "At the station, a man forcibly pulled my phone from my hand and ran into the crowd.",
        "Bike par aaye aadmi ne achanak mera handbag haath se jhatke se chheen liya aur bhaag gaya.",
        "एक व्यक्ति ने अचानक मेरे हाथ से मोबाइल जोर से छीना और तुरंत भाग गया।",
    ],
    "BNS_316": [
        "I entrusted my camera to a rental agent only for delivery to a customer. The agent instead sold it and kept the proceeds.",
        "Our treasurer was entrusted with society maintenance funds for depositing in the bank, but transferred the money to his personal account.",
        "Maine mechanic ko bike sirf repair ke liye di thi. Usne bike kisi aur ko bech di aur paise rakh liye.",
        "मैंने गोदाम मालिक को सामान सुरक्षित रखने के लिए सौंपा था, पर उसने जानबूझकर उसे बेच दिया।",
    ],
    "BNS_318": [
        "A seller advertised a camera he never possessed, accepted my payment, immediately deleted the account and admitted he had never intended to deliver anything.",
        "A broker knowingly showed me fabricated facts about a nonexistent plot and induced me to pay an advance, then disappeared.",
        "Seller ne shuru se jhooth bola ki product stock mein hai, payment lete hi number block kar diya aur delivery ka kabhi irada nahi tha.",
        "उसने नकली निवेश योजना बताकर शुरू से धोखे की नीयत से मुझसे पैसे जमा करवाए और तुरंत संपर्क बंद कर दिया।",
    ],
    "BNS_319": [
        "A man visited my parents pretending to be my authorised financial adviser and, using that false identity, induced them to hand over cash.",
        "Someone called my supplier while pretending to be me and convinced the supplier to release goods to him.",
        "Ek vyakti mere bhai bankar landlord ke paas gaya aur jhoothi pehchan se security deposit le gaya.",
        "एक व्यक्ति ने स्वयं को सरकारी अधिकारी बताकर मेरी मां को धोखा दिया और उनसे दस्तावेज ले लिए।",
    ],
    "BNS_329": [
        "After being told to leave, a stranger climbed through my kitchen window at night intending to intimidate me and remained inside the house.",
        "A former contractor entered our locked warehouse without permission intending to damage the stock, but security stopped him before he touched anything.",
        "Mana karne ke baad bhi padosi meri private office cabin mein ghus gaya aur mujhe daraane ke irade se wahin ruk gaya.",
        "एक व्यक्ति बिना अनुमति मेरे घर में अपमानित और डराने के इरादे से घुसा और कहने पर भी बाहर नहीं गया।",
    ],
    "BNS_351": [
        "A person threatened to burn my shop unless I withdrew my police complaint. The threat caused alarm and was recorded.",
        "My neighbour threatened to seriously injure my daughter to force me to sign a document I was not legally required to sign.",
        "Usne message bheja ki agar maine gawahi di to woh meri gaadi jala dega. Is dhamki se mujhe sach mein alarm hua.",
        "उसने मेरी प्रतिष्ठा नष्ट करने की धमकी देकर मुझे शिकायत वापस लेने के लिए मजबूर करने की कोशिश की।",
    ],
    "ITA_65": [
        "A system administrator knowingly deleted the original source-code files that our company is legally required to preserve for inspection, to conceal his unauthorised changes.",
        "An employee intentionally altered a computer source document that a regulatory direction required the business to maintain unchanged.",
        "Developer ne jaanbujhkar legally-required source code record chhupa diya aur audit se pehle uski copies destroy kar di.",
        "कर्मचारी ने उस कंप्यूटर स्रोत दस्तावेज को जानबूझकर बदल दिया जिसे कानून के तहत सुरक्षित रखना आवश्यक था।",
    ],
    "ITA_66": [
        "An intruder accessed our server without permission, deleted customer records and disrupted the system, causing financial loss. Logs show the access was deliberate.",
        "Someone fraudulently entered my cloud account without authorisation and downloaded confidential files from it.",
        "Kisi ne bina permission company network access karke data delete kiya aur service ko jaanbujhkar disrupt kar diya.",
        "किसी व्यक्ति ने बेईमानी से मेरे कंप्यूटर खाते में अनधिकृत प्रवेश किया और निजी डेटा डाउनलोड किया।",
    ],
    "ITA_66B": [
        "A dealer bought a stolen smartphone after being shown its theft report and then knowingly kept it for resale.",
        "My colleague received a stolen laptop from the thief at a suspiciously low price and admitted that he knew it had been stolen.",
        "Usne chori ka tablet jaante hue chor se liya aur serial number mita kar apne paas rakha.",
        "दुकानदार ने चोरी का मोबाइल जानते हुए प्राप्त किया और उसे बेचने के लिए अपने पास रखा।",
    ],
    "ITA_66C": [
        "My coworker fraudulently used my password to sign into the payroll portal as me and change my bank details.",
        "Someone dishonestly used my Aadhaar-linked authentication credential to complete an online verification in my name.",
        "Usne mera OTP aur login password use karke meri identity mein account access kiya.",
        "किसी ने मेरे पासवर्ड और डिजिटल हस्ताक्षर का धोखाधड़ी से उपयोग करके मेरे नाम से आवेदन जमा किया।",
    ],
    "ITA_66D": [
        "A caller used a phone to pretend to be a bank fraud officer and deceived me into sending money to a so-called safe account.",
        "Through a messaging app, someone impersonated an online marketplace employee and cheated me into paying a fake verification fee.",
        "WhatsApp par bank employee bankar usne mujhe fake payment link par paise bhejne ke liye dhokha diya.",
        "किसी ने वीडियो कॉल पर पुलिस अधिकारी बनकर धोखा दिया और मुझसे ऑनलाइन जुर्माना जमा करवाया।",
    ],
    "ITA_67": [
        "A website operator knowingly published lascivious electronic images intended to appeal to prurient interest; the images did not depict any sexually explicit act.",
        "A group administrator repeatedly transmitted obscene electronic cartoons likely to deprave viewers, but they contained no sexually explicit conduct.",
        "Usne online obscene aur lascivious images publish ki, lekin unmein koi sexually explicit act depict nahi tha.",
        "उसने इलेक्ट्रॉनिक रूप में अश्लील चित्र प्रसारित किए जो कामुक रुचि जगाते थे, पर उनमें कोई स्पष्ट यौन कृत्य नहीं था।",
    ],
    "ITA_67A": [
        "A person knowingly uploaded a video showing a sexually explicit act to a public website without consent.",
        "The administrator transmitted a recording containing explicit sexual conduct through a paid messaging channel.",
        "Usne sexually explicit act wala video electronic form mein group par publish aur transmit kiya.",
        "एक व्यक्ति ने स्पष्ट यौन कृत्य वाला वीडियो जानबूझकर ऑनलाइन प्रकाशित किया।",
    ],
}

for provision_id, complaints in SINGLE.items():
    if len(complaints) != 4:
        raise ValueError(f"{provision_id} does not have four cases")
    for index, complaint in enumerate(complaints):
        language = "en" if index < 2 else ("hinglish" if index == 2 else "hi")
        optional = ()
        if provision_id == "BNS_304":
            optional = ("BNS_303",)
        elif provision_id == "ITA_66C":
            optional = ("ITA_66",)
        elif provision_id == "ITA_66D":
            optional = ("BNS_319",)
        add("single_provision", complaint, "provision_match", (provision_id,), optional,
            language=language, difficulty="standard",
            rationale=f"Facts directly state the distinguishing elements of {provision_id}.")


MULTI = [
    ("A fraudster used my stolen online-banking password to enter my account and transfer funds without permission.", ("ITA_66", "ITA_66C"), ()),
    ("Someone created a fake profile in my name, impersonated me in messages and cheated my cousin into transferring money.", ("BNS_319", "ITA_66C", "ITA_66D"), ("BNS_318",)),
    ("A caller pretended to be my bank manager, used my OTP as my credential and deceived me into approving a transfer.", ("BNS_319", "ITA_66C", "ITA_66D"), ("BNS_318",)),
    ("An administrator illegally entered the production server and intentionally altered source-code records that the company is legally required to preserve.", ("ITA_65", "ITA_66"), ()),
    ("A man secretly recorded a woman engaged in a sexual act in a private room and then transmitted the explicit video online.", ("BNS_77", "ITA_67A"), ()),
    ("Someone transmitted a sexually explicit video of me and threatened to send it to my employer unless I withdrew my complaint.", ("BNS_351", "ITA_67A"), ()),
    ("A stranger entered my locked home intending to steal and then carried away my television without consent.", ("BNS_329", "BNS_303"), ()),
    ("A man entered my house without permission intending to attack me and deliberately punched me, causing ordinary bruising.", ("BNS_329", "BNS_115"), ()),
    ("My neighbour intentionally slapped me and then threatened to burn my car if I reported the assault.", ("BNS_115", "BNS_351"), ()),
    ("An attacker deliberately fractured my wrist and threatened to harm my family if I gave evidence.", ("BNS_117", "BNS_351"), ()),
    ("An agent obtained my jewellery by falsely claiming it would be valued, although he intended from the start to sell it; after I entrusted it, he sold it and kept the proceeds.", ("BNS_316", "BNS_318"), ()),
    ("Using a messaging app, a fraudster impersonated my employer and induced me to send money to his account.", ("BNS_319", "ITA_66D"), ("BNS_318",)),
    ("A male coworker made repeated sexual demands and, after I refused, followed me home on several days despite being told to stop.", ("BNS_75", "BNS_78"), ()),
    ("A man secretly recorded me during a private act and threatened to publish the recording unless I resigned.", ("BNS_77", "BNS_351"), ()),
    ("A person published obscene electronic images about me and separately threatened to damage my house if I asked for their removal.", ("ITA_67", "BNS_351"), ()),
    ("An intruder hacked my social-media account and used it to publish a video containing a sexually explicit act.", ("ITA_66", "ITA_67A"), ()),
    ("A man suddenly yanked my handbag away and intentionally shoved me during the snatching, causing bruises but no fracture.", ("BNS_304", "BNS_115"), ("BNS_303",)),
    ("A rider forcibly grabbed my bag; the force threw me down and fractured my arm, as confirmed by X-ray.", ("BNS_304", "BNS_117"), ("BNS_303",)),
    ("Two people broke into our warehouse and removed stored equipment without the owner's consent.", ("BNS_329", "BNS_303"), ()),
    ("A dealer knowingly received a stolen laptop and then deceived a buyer by selling it as a new, lawfully owned device.", ("ITA_66B", "BNS_318"), ()),
    ("A person used my password and then pretended to be me in emails to obtain confidential records from my office.", ("ITA_66C", "BNS_319"), ("ITA_66D",)),
    ("A manager demanded a sexual favour and threatened to terminate my job unless I complied.", ("BNS_75", "BNS_351"), ()),
    ("After I rejected him, a man hacked my email account so that he could continue monitoring my private communications.", ("BNS_78", "ITA_66"), ()),
    ("A repair agent entrusted with my phone pretended to be its owner and sold it to another person, keeping the money.", ("BNS_316", "BNS_319"), ()),
]
for index, (complaint, required, optional) in enumerate(MULTI):
    add("multi_provision", complaint, "provision_match", required, optional,
        language="en", difficulty="hard",
        rationale="The incident contains independent factual elements for each required provision.")


MISSING = [
    ("My manager said something that made me uncomfortable, but I have not explained what was said or whether it was sexual.", "BNS_75"),
    ("I found a small camera near a changing area, but I do not know whether it recorded anyone or who installed it.", "BNS_77"),
    ("The same person was near my workplace once. I do not know whether he followed me, contacted me, or monitored me online.", "BNS_78"),
    ("I was injured yesterday, but I have not described who caused it, whether it was intentional, or what the injury was.", "BNS_115"),
    ("Someone hit me, but no medical examination has occurred and I cannot yet describe whether there was a fracture or another grievous injury.", "BNS_117"),
    ("My wallet is missing after a trip. I may have dropped it and did not see anyone take it.", "BNS_303"),
    ("My bag disappeared in a crowd, but I did not see whether anyone suddenly or forcibly grabbed it or whether I left it behind.", "BNS_304"),
    ("A repair shop still has my laptop one day after the estimated date, but I do not know whether it was sold, converted, or simply delayed.", "BNS_316"),
    ("A product I paid for is late. The seller remains reachable and says it is delayed, and I have no facts showing dishonest intention at the time of payment.", "BNS_318"),
    ("An account with a bank logo messaged me, but I do not know who controlled it or whether anyone pretended to be a particular person.", "BNS_319"),
    ("A person entered a corridor shared by several tenants. I do not know whether he lacked permission or intended to intimidate, insult, annoy, or commit an offence.", "BNS_329"),
    ("A message said 'you will regret this,' but it did not identify any injury to a person, reputation, or property and I do not know what was intended.", "BNS_351"),
    ("A source-code file changed, but I do not know who changed it or whether the file was legally required to be kept or maintained.", "ITA_65"),
    ("My computer became slow, but there are no access logs or facts showing unauthorised access, deletion, disruption, or fraudulent conduct.", "ITA_66"),
    ("I bought a used phone at an ordinary price. I do not know whether it was stolen or whether the seller or buyer knew of any theft.", "ITA_66B"),
    ("My password stopped working, but I have no login alert or evidence that another person used the password or another identifying credential.", "ITA_66C"),
    ("A caller asked me to pay a fee, but I do not know whether the caller impersonated anyone or used a false identity.", "ITA_66D"),
    ("A picture was forwarded in a group, but I have not seen it and do not know whether it was obscene or appealed to prurient interest.", "ITA_67"),
    ("Someone referred to an 'intimate clip,' but I do not know whether it contained a sexually explicit act or whether it was electronically transmitted.", "ITA_67A"),
    ("Mera phone nahi mil raha; mujhe nahi pata kisi ne churaya, chheena, ya main kahin bhool gaya.", "BNS_303"),
    ("Seller ne delivery delay bataya hai aur contact mein hai; mere paas shuru se fraud intention ka koi fact nahi hai.", "BNS_318"),
    ("Mera email login fail ho raha hai, par unauthorized access ya password misuse ka koi alert nahi mila.", "ITA_66"),
    ("एक व्यक्ति दो बार मेरे रास्ते में दिखा, पर उसने संपर्क नहीं किया और मुझे नहीं पता कि वह मेरा पीछा कर रहा था।", "BNS_78"),
    ("मेरी वस्तु मरम्मत की दुकान पर है और वापसी में देरी हुई है, पर बेचने या हड़पने की कोई जानकारी नहीं है।", "BNS_316"),
    ("एक वीडियो का उल्लेख हुआ है, लेकिन यह स्पष्ट नहीं है कि उसमें कोई यौन कृत्य है या उसे ऑनलाइन भेजा गया।", "ITA_67A"),
]
for index, (complaint, uncertain_id) in enumerate(MISSING):
    language = "en" if index < 19 else ("hinglish" if index < 22 else "hi")
    add("missing_information", complaint, "insufficient_information",
        uncertain=(uncertain_id,), language=language, difficulty="hard",
        rationale=f"A material fact needed to assess {uncertain_id} is genuinely absent.")


OUT_OF_SCOPE = [
    "My professor awarded fewer marks than I expected, and I want a criminal section applied even though there were no threats, forged records, or bribery.",
    "My internet speed has been poor for two days despite payment, and the provider says maintenance is underway.",
    "My landlord and I disagree about reasonable cleaning deductions from the deposit; no one lied, threatened anyone, or forged the agreement.",
    "A restaurant meal arrived cold and I want the chef arrested, although the restaurant offered a replacement.",
    "My friend has stopped replying to messages. There were no threats, money demands, stalking, or access to my accounts.",
    "A company rejected my job application without giving a reason. I have no facts suggesting deception, threats, or unlawful access.",
    "A courier delivery is one day late and tracking still shows it in transit. No one has demanded additional money or disappeared.",
    "My neighbour painted his own wall a colour I dislike. He did not enter my property or damage anything belonging to me.",
    "I lost a board game at a club match and believe the rules were unfair, but there was no cheating involving property or false identity.",
    "A shop charged the displayed price, but I later found the same product cheaper elsewhere. No representation about competitors' prices was made.",
    "My adult sibling chose not to attend a family event, and I want the police to force attendance.",
    "A streaming service removed a film I planned to watch and issued the contractual refund.",
    "My manager gave me an average performance rating. No sexual remarks, threats, forged documents, or false allegations were involved.",
    "A train was delayed because of weather and I missed an appointment. There is no allegation of theft, deception, or sabotage.",
    "A seller cancelled my order before taking payment and explained that the item was out of stock.",
    "Mere dost ne party invite nahi kiya. Koi threat, fraud, paisa, stalking ya account access ka matter nahi hai.",
    "Internet plan ki speed advertisement se kam lag rahi hai, provider complaint investigate kar raha hai aur koi dishonest claim ka fact nahi hai.",
    "Landlord ne agreement ke mutabik rent badhane ka notice diya; koi dhamki, jhooth ya forged document nahi hai.",
    "College team ne mujhe select nahi kiya aur reason performance bataya. Koi bribe, threat ya fake record ka allegation nahi hai.",
    "Restaurant ne galat dish bheji lekin turant refund kar diya; koi deception ya criminal threat nahi hua.",
    "विश्वविद्यालय की लाइब्रेरी ने देर से किताब लौटाने पर नियम के अनुसार जुर्माना लगाया है। कोई धोखा या धमकी नहीं हुई।",
    "मेरा मोबाइल नेटवर्क कुछ घंटों से धीमा है और कंपनी मरम्मत कर रही है। किसी ने खाते में प्रवेश नहीं किया।",
    "मेरे पड़ोसी ने अपने घर के सामने गाड़ी खड़ी की जो कानूनी पार्किंग स्थान है। उसने मेरी संपत्ति में प्रवेश नहीं किया।",
    "दुकान ने भुगतान लेने से पहले ऑर्डर रद्द कर दिया और कोई पैसा नहीं लिया।",
    "मेरे सहकर्मी ने बैठक में मेरी राय से असहमति जताई, लेकिन कोई धमकी, यौन टिप्पणी या झूठी पहचान नहीं थी।",
]
for index, complaint in enumerate(OUT_OF_SCOPE):
    language = "en" if index < 15 else ("hinglish" if index < 20 else "hi")
    add("out_of_scope", complaint, "out_of_scope", language=language,
        difficulty="hard_negative",
        rationale="The stated dispute contains no factual element of a recommendation-approved criminal provision.")


if len(cases) != 150:
    raise AssertionError(f"Expected 150 cases, found {len(cases)}")
if len({case["complaint"].casefold() for case in cases}) != len(cases):
    raise AssertionError("Duplicate benchmark complaints")


def user_texts_from_training_zip() -> list[tuple[str, str]]:
    collected = []
    with zipfile.ZipFile(TRAINING_ZIP) as archive:
        names = [
            "colab_training_input_v5/complaint_only/train_sft.jsonl",
            "colab_training_input_v5/complaint_only/dev_sft.jsonl",
            "colab_training_input_v5/evaluation/sealed_test.jsonl",
        ]
        for name in names:
            for line in archive.read(name).decode("utf-8").splitlines():
                row = json.loads(line)
                for message in row["messages"]:
                    if message.get("role") == "user":
                        collected.append((name, message["content"]))
                        break
    if OLD_MANUAL_RESULTS.is_file():
        payload = json.loads(OLD_MANUAL_RESULTS.read_text(encoding="utf-8"))
        for row in payload["comparisons"]:
            collected.append(("manual_21", row["complaint"]))
    return collected


def tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"\w+", text.casefold(), flags=re.UNICODE)
            if token.strip("_")}


reference_texts = user_texts_from_training_zip()
reference_tokens = [(source, text, tokens(text)) for source, text in reference_texts]
overlap_rows = []
for case in cases:
    current = tokens(case["complaint"])
    best = (0.0, "", "")
    for source, text, other in reference_tokens:
        union = current | other
        score = len(current & other) / len(union) if union else 1.0
        if score > best[0]:
            best = (score, source, text)
    overlap_rows.append({
        "case_id": case["case_id"],
        "max_token_jaccard": round(best[0], 6),
        "nearest_source": best[1],
        "nearest_text_preview": best[2][:240],
    })

exact_reference = {text.casefold().strip() for _, text in reference_texts}
if any(case["complaint"].casefold().strip() in exact_reference for case in cases):
    raise AssertionError("Benchmark contains an exact training/dev/old-test complaint")
if max(row["max_token_jaccard"] for row in overlap_rows) >= 0.72:
    worst = max(overlap_rows, key=lambda row: row["max_token_jaccard"])
    raise AssertionError(f"Benchmark similarity is too high: {worst}")

OUTPUT.mkdir(parents=True, exist_ok=True)
public_rows = [{key: case[key] for key in ("case_id", "group", "language", "difficulty", "complaint")}
               for case in cases]
gold_rows = [{"case_id": case["case_id"], **case["gold"]} for case in cases]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
                    encoding="utf-8")


public_path = OUTPUT / "benchmark_inputs.jsonl"
gold_path = OUTPUT / "sealed_answer_key.jsonl"
overlap_path = OUTPUT / "separation_report.json"
write_jsonl(public_path, public_rows)
write_jsonl(gold_path, gold_rows)
overlap_path.write_text(json.dumps({
    "reference_complaints": len(reference_texts),
    "exact_overlap_count": 0,
    "maximum_token_jaccard": max(row["max_token_jaccard"] for row in overlap_rows),
    "rows": overlap_rows,
}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


manifest = {
    "benchmark": "sealed_rag_benchmark_v1",
    "status": "frozen_before_first_model_run",
    "created_by": "AI review against verified statutory catalogue; not lawyer-verified",
    "counts": {
        "total": len(cases),
        "groups": dict(Counter(case["group"] for case in cases)),
        "languages": dict(Counter(case["language"] for case in cases)),
        "positive_single": 76,
        "positive_multi": 24,
        "missing_information": 25,
        "out_of_scope": 25,
    },
    "scope": {
        "recommendation_approved_provisions": sorted(RECOMMENDABLE),
        "provision_count": len(RECOMMENDABLE),
    },
    "separation": {
        "reference_complaints": len(reference_texts),
        "exact_overlap_count": 0,
        "maximum_token_jaccard": max(row["max_token_jaccard"] for row in overlap_rows),
        "threshold": 0.72,
        "includes_old_manual_21_in_reference": True,
    },
    "files_sha256": {
        public_path.name: sha256(public_path),
        gold_path.name: sha256(gold_path),
        overlap_path.name: sha256(overlap_path),
    },
    "scoring": {
        "strict_exact_sections": "predicted section set equals required section set",
        "acceptable_sections": "all required sections present and predictions contain only required or optional sections",
        "gold_is_never_added_to_model_prompts": True,
    },
}
(OUTPUT / "manifest.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(manifest, indent=2, ensure_ascii=False))

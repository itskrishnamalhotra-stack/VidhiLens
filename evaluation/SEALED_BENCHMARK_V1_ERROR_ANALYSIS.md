# Sealed benchmark v1 error analysis

- Cases: 150
- Cases with any gold disagreement: 45
- Required-section miss stages: `{"candidate_assessor_rejected": 4, "evidence_gate_removed_or_downgraded": 4, "retrieval_miss": 13}`
- Outcome transitions: `{"insufficient_information -> out_of_scope": 4, "insufficient_information -> provision_match": 1, "out_of_scope -> insufficient_information": 1, "provision_match -> insufficient_information": 4, "provision_match -> out_of_scope": 2}`

## Case details

### SRB1_004 — single_provision — hi

एक पुरुष प्रशिक्षक ने महिला खिलाड़ी से चयन के बदले यौन संबंध की मांग की। उसने साफ मना किया और बातचीत रिकॉर्ड है।

- Gold outcome: `provision_match`
- Required: `BNS_75`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_69"], "uncertain_sections": []}`
- Retrieved: `BNS_69`
- RAG v2.2: `{"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}`
- Miss `BNS_75`: **retrieval_miss** — 

### SRB1_009 — single_provision — en

After I repeatedly asked a man to stop contacting me, he followed me from college to my home on four days and waited outside the gate.

- Gold outcome: `provision_match`
- Required: `BNS_78`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_351"], "uncertain_sections": []}`
- Retrieved: `BNS_78, BNS_351, BNS_64`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_351"], "uncertain_sections": []}`
- Miss `BNS_78`: **candidate_assessor_rejected** — The incident describes follow-up and monitoring of a person's location, but does not involve repeated contact or attempts to foster personal interaction despite clear disinterest.
- Extra `BNS_351` — The man followed the complainant from college to home and waited outside the gate after repeated requests to stop contacting, indicating intent to cause alarm or distress.

### SRB1_026 — single_provision — en

At the station, a man forcibly pulled my phone from my hand and ran into the crowd.

- Gold outcome: `provision_match`
- Required: `BNS_304`
- Optional: `BNS_303`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_130"], "uncertain_sections": []}`
- Retrieved: `(none)`
- RAG v2.2: `{"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}`
- Miss `BNS_304`: **retrieval_miss** — 

### SRB1_029 — single_provision — en

I entrusted my camera to a rental agent only for delivery to a customer. The agent instead sold it and kept the proceeds.

- Gold outcome: `provision_match`
- Required: `BNS_316`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_316"], "uncertain_sections": []}`
- Retrieved: `BNS_316, BNS_314, BNS_318, BNS_317, BNS_334, BNS_303`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_316", "BNS_318"], "uncertain_sections": []}`
- Extra `BNS_318` — The agent sold the camera without authorization and kept the proceeds, constituting dishonest deception inducing delivery of property.

### SRB1_030 — single_provision — en

Our treasurer was entrusted with society maintenance funds for depositing in the bank, but transferred the money to his personal account.

- Gold outcome: `provision_match`
- Required: `BNS_316`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_316"], "uncertain_sections": []}`
- Retrieved: `BNS_316, BNS_314, BNS_315, BNS_317, BNS_196, BNS_303`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_316", "BNS_303"], "uncertain_sections": []}`
- Extra `BNS_303` — The treasurer moved the society maintenance funds to his personal account without consent, intending to take them dishonestly.

### SRB1_033 — single_provision — en

A seller advertised a camera he never possessed, accepted my payment, immediately deleted the account and admitted he had never intended to deliver anything.

- Gold outcome: `provision_match`
- Required: `BNS_318`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_318"], "uncertain_sections": []}`
- Retrieved: `BNS_318, BNS_315, BNS_338, BNS_308, BNS_316, BNS_334`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_318", "BNS_316"], "uncertain_sections": []}`
- Extra `BNS_316` — The seller advertised a camera he never possessed, accepted payment, and admitted never intending to deliver, showing dishonest misappropriation of trust in property.

### SRB1_036 — single_provision — hi

उसने नकली निवेश योजना बताकर शुरू से धोखे की नीयत से मुझसे पैसे जमा करवाए और तुरंत संपर्क बंद कर दिया।

- Gold outcome: `provision_match`
- Required: `BNS_318`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_319"], "uncertain_sections": []}`
- Retrieved: `BNS_319`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_319"], "uncertain_sections": []}`
- Miss `BNS_318`: **retrieval_miss** — 
- Extra `BNS_319` — The accused pretended to be a person (a certain rich banker) and induced the complainant to deposit money, which constitutes cheating by personation.

### SRB1_038 — single_provision — en

Someone called my supplier while pretending to be me and convinced the supplier to release goods to him.

- Gold outcome: `provision_match`
- Required: `BNS_319`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_319"], "uncertain_sections": []}`
- Retrieved: `BNS_319, ITA_66C, ITA_66D, ITA_66B, ITA_69B, ITA_69`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_319", "ITA_66D"], "uncertain_sections": [{"provision_id": "ITA_66C", "missing_facts": "Did the person fraudulently use your password, electronic signature, or another unique identification feature?"}]}`
- Extra `ITA_66D` — The caller pretended to be the complainant and used a communication device to deceive the supplier into releasing goods.

### SRB1_049 — single_provision — en

A system administrator knowingly deleted the original source-code files that our company is legally required to preserve for inspection, to conceal his unauthorised changes.

- Gold outcome: `provision_match`
- Required: `ITA_65`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_65"], "uncertain_sections": []}`
- Retrieved: `ITA_66, ITA_66C, ITA_65, ITA_69B, ITA_66F, ITA_69A`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66", "ITA_65"], "uncertain_sections": []}`
- Extra `ITA_66` — The administrator knowingly deleted the original source-code files with intent to conceal unauthorized changes, constituting dishonest and fraudulent alteration of computer source code.

### SRB1_050 — single_provision — en

An employee intentionally altered a computer source document that a regulatory direction required the business to maintain unchanged.

- Gold outcome: `provision_match`
- Required: `ITA_65`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_65"], "uncertain_sections": []}`
- Retrieved: `BNS_303, BNS_304, BNS_305, ITA_65, BNS_328`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_303", "ITA_65"], "uncertain_sections": []}`
- Extra `BNS_303` — The employee intentionally altered a regulatory document required to be maintained unchanged, with intent to take it dishonestly out of possession without consent.

### SRB1_054 — single_provision — en

Someone fraudulently entered my cloud account without authorisation and downloaded confidential files from it.

- Gold outcome: `provision_match`
- Required: `ITA_66`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66C"], "uncertain_sections": []}`
- Retrieved: `ITA_66C`
- RAG v2.2: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"provision_id": "ITA_66C", "missing_facts": "Did the person fraudulently use your password, electronic signature, or another unique identification feature?"}]}`
- Miss `ITA_66`: **retrieval_miss** — 

### SRB1_056 — single_provision — hi

किसी व्यक्ति ने बेईमानी से मेरे कंप्यूटर खाते में अनधिकृत प्रवेश किया और निजी डेटा डाउनलोड किया।

- Gold outcome: `provision_match`
- Required: `ITA_66`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66C"], "uncertain_sections": []}`
- Retrieved: `ITA_66C`
- RAG v2.2: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"provision_id": "ITA_66C", "missing_facts": "Did the person fraudulently use your password, electronic signature, or another unique identification feature?"}]}`
- Miss `ITA_66`: **retrieval_miss** — 

### SRB1_057 — single_provision — en

A dealer bought a stolen smartphone after being shown its theft report and then knowingly kept it for resale.

- Gold outcome: `provision_match`
- Required: `ITA_66B`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66B"], "uncertain_sections": []}`
- Retrieved: `BNS_303, BNS_304, BNS_305, ITA_66B, BNS_317, BNS_306`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_303", "ITA_66B"], "uncertain_sections": []}`
- Extra `BNS_303` — The dealer knowingly acquired and kept a stolen smartphone, intending to take it dishonestly out of the possession of the original owner without consent.

### SRB1_058 — single_provision — en

My colleague received a stolen laptop from the thief at a suspiciously low price and admitted that he knew it had been stolen.

- Gold outcome: `provision_match`
- Required: `ITA_66B`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66B"], "uncertain_sections": []}`
- Retrieved: `BNS_303, BNS_304, BNS_305, ITA_66B, BNS_317, BNS_252`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_303", "ITA_66B"], "uncertain_sections": []}`
- Extra `BNS_303` — The colleague received a stolen laptop at a suspiciously low price and admitted knowing it was stolen, indicating intent to take dishonestly without consent.

### SRB1_061 — single_provision — en

My coworker fraudulently used my password to sign into the payroll portal as me and change my bank details.

- Gold outcome: `provision_match`
- Required: `ITA_66C`
- Optional: `ITA_66`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66C"], "uncertain_sections": []}`
- Retrieved: `ITA_66, ITA_66C, ITA_66D, ITA_69B, ITA_69, ITA_66B`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66", "ITA_66C", "ITA_66D"], "uncertain_sections": []}`
- Extra `ITA_66D` — The coworker used the password to log in as the complainant and alter bank details, constituting personation by means of a computer resource.

### SRB1_063 — single_provision — hinglish

Usne mera OTP aur login password use karke meri identity mein account access kiya.

- Gold outcome: `provision_match`
- Required: `ITA_66C`
- Optional: `ITA_66`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66C"], "uncertain_sections": []}`
- Retrieved: `ITA_66, ITA_66C, ITA_66D, ITA_69A, ITA_69B, ITA_69`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66", "ITA_66D"], "uncertain_sections": [{"provision_id": "ITA_66C", "missing_facts": "Did the person fraudulently use your password, electronic signature, or another unique identification feature?"}]}`
- Miss `ITA_66C`: **evidence_gate_removed_or_downgraded** — The incident describes unauthorized use of OTP and login password, which are unique identification features of the person, to access the account.
- Extra `ITA_66D` — The incident involves unauthorized use of OTP and login password to access the account, constituting personation by means of computer resource.

### SRB1_064 — single_provision — hi

किसी ने मेरे पासवर्ड और डिजिटल हस्ताक्षर का धोखाधड़ी से उपयोग करके मेरे नाम से आवेदन जमा किया।

- Gold outcome: `provision_match`
- Required: `ITA_66C`
- Optional: `ITA_66`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66C"], "uncertain_sections": []}`
- Retrieved: `ITA_66C`
- RAG v2.2: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"provision_id": "ITA_66C", "missing_facts": "Did the person fraudulently use your password, electronic signature, or another unique identification feature?"}]}`
- Miss `ITA_66C`: **evidence_gate_removed_or_downgraded** — The incident describes fraudulent use of password and digital signature in another person's name, which matches the definition of identity theft.

### SRB1_073 — single_provision — en

A person knowingly uploaded a video showing a sexually explicit act to a public website without consent.

- Gold outcome: `provision_match`
- Required: `ITA_67A`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_67A"], "uncertain_sections": []}`
- Retrieved: `ITA_67A, ITA_67B, BNS_75, BNS_67, ITA_67, BNS_69`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_67A", "ITA_67"], "uncertain_sections": []}`
- Extra `ITA_67` — The video shows a sexually explicit act and was uploaded to a public website without consent, which constitutes publication of material appealing to prurient interest.

### SRB1_074 — single_provision — en

The administrator transmitted a recording containing explicit sexual conduct through a paid messaging channel.

- Gold outcome: `provision_match`
- Required: `ITA_67A`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_67A"], "uncertain_sections": []}`
- Retrieved: `ITA_67A, BNS_75, ITA_67B, ITA_67, BNS_69, BNS_67`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_67"], "uncertain_sections": [{"provision_id": "ITA_67A", "missing_facts": "Did the transmitted material contain a sexually explicit act or conduct?"}]}`
- Miss `ITA_67A`: **evidence_gate_removed_or_downgraded** — The recording contains explicit sexual conduct and was transmitted through a paid messaging channel, matching the definition of sexually explicit material in electronic form.
- Extra `ITA_67` — The recording contains explicit sexual conduct and was transmitted through a paid messaging channel, which may appeal to prurient interest and tend to deprave.

### SRB1_075 — single_provision — hinglish

Usne sexually explicit act wala video electronic form mein group par publish aur transmit kiya.

- Gold outcome: `provision_match`
- Required: `ITA_67A`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_67A"], "uncertain_sections": []}`
- Retrieved: `ITA_67A, ITA_67B, BNS_75, ITA_67, BNS_69, BNS_67`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_67A", "ITA_67"], "uncertain_sections": []}`
- Extra `ITA_67` — The incident describes publishing and transmitting a sexually explicit video in electronic form, which falls under obscene material as defined in the provision.

### SRB1_076 — single_provision — hi

एक व्यक्ति ने स्पष्ट यौन कृत्य वाला वीडियो जानबूझकर ऑनलाइन प्रकाशित किया।

- Gold outcome: `provision_match`
- Required: `ITA_67A`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_67A"], "uncertain_sections": []}`
- Retrieved: `ITA_67A`
- RAG v2.2: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"provision_id": "ITA_67A", "missing_facts": "Did the transmitted material contain a sexually explicit act or conduct?"}]}`
- Miss `ITA_67A`: **evidence_gate_removed_or_downgraded** — The incident involves deliberate online publication of a video containing sexual explicit act.

### SRB1_077 — multi_provision — en

A fraudster used my stolen online-banking password to enter my account and transfer funds without permission.

- Gold outcome: `provision_match`
- Required: `ITA_66, ITA_66C`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66C"], "uncertain_sections": []}`
- Retrieved: `BNS_303, BNS_304, BNS_305, ITA_66, ITA_66C, ITA_66D`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_303", "ITA_66", "ITA_66C"], "uncertain_sections": []}`
- Extra `BNS_303` — The fraudster used the stolen password to access the account and transfer funds without consent, constituting dishonest taking of movable property.

### SRB1_079 — multi_provision — en

A caller pretended to be my bank manager, used my OTP as my credential and deceived me into approving a transfer.

- Gold outcome: `provision_match`
- Required: `BNS_319, ITA_66C, ITA_66D`
- Optional: `BNS_318`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66C"], "uncertain_sections": []}`
- Retrieved: `ITA_66, ITA_66C, ITA_66D, ITA_69B, ITA_69, ITA_66B`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66C", "ITA_66D"], "uncertain_sections": [{"provision_id": "ITA_66", "missing_facts": "Did the caller access or secure access to the bank's computer system or network to obtain the OTP?; Was the act of obtaining OTP through deception considered as accessing or securing access to a computer resource without permission?"}]}`
- Miss `BNS_319`: **retrieval_miss** — 

### SRB1_081 — multi_provision — en

A man secretly recorded a woman engaged in a sexual act in a private room and then transmitted the explicit video online.

- Gold outcome: `provision_match`
- Required: `BNS_77, ITA_67A`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_77"], "uncertain_sections": []}`
- Retrieved: `BNS_77, BNS_75, ITA_67B, ITA_67A, ITA_67, BNS_81`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_77", "ITA_67A", "ITA_67"], "uncertain_sections": []}`
- Extra `ITA_67` — The transmission of explicit video that appeals to prurient interest and tends to deprave or corrupt persons constitutes publication of obscene material in electronic form.

### SRB1_082 — multi_provision — en

Someone transmitted a sexually explicit video of me and threatened to send it to my employer unless I withdrew my complaint.

- Gold outcome: `provision_match`
- Required: `BNS_351, ITA_67A`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_78"], "uncertain_sections": []}`
- Retrieved: `BNS_308, BNS_351, BNS_78, BNS_75, ITA_67B, ITA_67A`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_351"], "uncertain_sections": []}`
- Miss `ITA_67A`: **candidate_assessor_rejected** — The incident involves threats and potential harassment, not the transmission of sexually explicit material in electronic form.

### SRB1_083 — multi_provision — en

A stranger entered my locked home intending to steal and then carried away my television without consent.

- Gold outcome: `provision_match`
- Required: `BNS_329, BNS_303`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_303"], "uncertain_sections": []}`
- Retrieved: `BNS_303, BNS_134, BNS_314, BNS_306, BNS_97, BNS_317`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_303"], "uncertain_sections": []}`
- Miss `BNS_329`: **retrieval_miss** — 

### SRB1_084 — multi_provision — en

A man entered my house without permission intending to attack me and deliberately punched me, causing ordinary bruising.

- Gold outcome: `provision_match`
- Required: `BNS_329, BNS_115`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_115"], "uncertain_sections": []}`
- Retrieved: `BNS_115, BNS_73`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_115"], "uncertain_sections": []}`
- Miss `BNS_329`: **retrieval_miss** — 

### SRB1_091 — multi_provision — en

A person published obscene electronic images about me and separately threatened to damage my house if I asked for their removal.

- Gold outcome: `provision_match`
- Required: `ITA_67, BNS_351`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_67"], "uncertain_sections": []}`
- Retrieved: `BNS_308, BNS_351, ITA_67, BNS_323, BNS_329, BNS_309`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_351", "ITA_67", "BNS_329"], "uncertain_sections": []}`
- Extra `BNS_329` — The person threatened to damage the house, which constitutes intimidation with intent to annoy or intimidate the occupant.

### SRB1_092 — multi_provision — en

An intruder hacked my social-media account and used it to publish a video containing a sexually explicit act.

- Gold outcome: `provision_match`
- Required: `ITA_66, ITA_67A`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_67A"], "uncertain_sections": []}`
- Retrieved: `ITA_66, ITA_66C, ITA_67A, ITA_67B, BNS_75, ITA_69B`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66"], "uncertain_sections": [{"provision_id": "ITA_66C", "missing_facts": "Did the person fraudulently use your password, electronic signature, or another unique identification feature?"}]}`
- Miss `ITA_67A`: **candidate_assessor_rejected** — The incident involves unauthorized access to a social media account, not the publication or transmission of material containing a sexually explicit act in electronic form.

### SRB1_093 — multi_provision — en

A man suddenly yanked my handbag away and intentionally shoved me during the snatching, causing bruises but no fracture.

- Gold outcome: `provision_match`
- Required: `BNS_304, BNS_115`
- Optional: `BNS_303`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_130"], "uncertain_sections": []}`
- Retrieved: `BNS_304, BNS_84`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_304"], "uncertain_sections": []}`
- Miss `BNS_115`: **retrieval_miss** — 

### SRB1_095 — multi_provision — en

Two people broke into our warehouse and removed stored equipment without the owner's consent.

- Gold outcome: `provision_match`
- Required: `BNS_329, BNS_303`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_303"], "uncertain_sections": []}`
- Retrieved: `BNS_303, BNS_314, BNS_89, BNS_306, BNS_315, BNS_317`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_303"], "uncertain_sections": []}`
- Miss `BNS_329`: **retrieval_miss** — 

### SRB1_096 — multi_provision — en

A dealer knowingly received a stolen laptop and then deceived a buyer by selling it as a new, lawfully owned device.

- Gold outcome: `provision_match`
- Required: `ITA_66B, BNS_318`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66B"], "uncertain_sections": []}`
- Retrieved: `BNS_303, BNS_304, BNS_305, ITA_66B, BNS_317, BNS_306`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_303", "ITA_66B"], "uncertain_sections": []}`
- Miss `BNS_318`: **retrieval_miss** — 
- Extra `BNS_303` — The dealer knowingly received a stolen laptop and sold it as lawfully owned, moving the property with dishonest intent without the owner's consent.

### SRB1_097 — multi_provision — en

A person used my password and then pretended to be me in emails to obtain confidential records from my office.

- Gold outcome: `provision_match`
- Required: `ITA_66C, BNS_319`
- Optional: `ITA_66D`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66C"], "uncertain_sections": []}`
- Retrieved: `ITA_66, ITA_66C, ITA_66D, ITA_69B, ITA_69, ITA_66B`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66", "ITA_66C", "ITA_66D"], "uncertain_sections": []}`
- Miss `BNS_319`: **retrieval_miss** — 
- Extra `ITA_66` — The person used the password and pretended to be the complainant to obtain confidential records, constituting dishonest and fraudulent access to a computer system.

### SRB1_099 — multi_provision — en

After I rejected him, a man hacked my email account so that he could continue monitoring my private communications.

- Gold outcome: `provision_match`
- Required: `BNS_78, ITA_66`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66C"], "uncertain_sections": []}`
- Retrieved: `ITA_66, ITA_66C, BNS_78, ITA_69B, ITA_69, ITA_66F`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["ITA_66"], "uncertain_sections": [{"provision_id": "ITA_66C", "missing_facts": "Did the person fraudulently use your password, electronic signature, or another unique identification feature?"}]}`
- Miss `BNS_78`: **candidate_assessor_rejected** — Stalking requires repeated contact or monitoring for personal interaction or to foster interaction, not unauthorized access to an email account for monitoring private communications.

### SRB1_100 — multi_provision — en

A repair agent entrusted with my phone pretended to be its owner and sold it to another person, keeping the money.

- Gold outcome: `provision_match`
- Required: `BNS_316, BNS_319`
- Optional: `(none)`
- LoRA: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_316"], "uncertain_sections": []}`
- Retrieved: `BNS_316, BNS_314, BNS_193, BNS_315, BNS_317, BNS_303`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_316"], "uncertain_sections": []}`
- Miss `BNS_319`: **retrieval_miss** — 

### SRB1_108 — missing_information — en

A repair shop still has my laptop one day after the estimated date, but I do not know whether it was sold, converted, or simply delayed.

- Gold outcome: `insufficient_information`
- Required: `(none)`
- Optional: `(none)`
- LoRA: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"provision_id": "ITA_66B", "missing_facts": "whether_property_was_delivered_or_transferred_from_owner_to_relevant_person_or_another_person"}]}`
- Retrieved: `BNS_316, BNS_314, ITA_66B, BNS_317, BNS_303, BNS_315`
- RAG v2.2: `{"outcome": "provision_match", "possible_provision_ids": ["BNS_316"], "uncertain_sections": [{"provision_id": "ITA_66B", "missing_facts": "Did the repair shop know the laptop was stolen?; Was the laptop sold, converted, or simply delayed without the owner's consent?"}, {"provision_id": "BNS_303", "missing_facts": "Did the repair shop take the laptop dishonestly with intent to deprive the owner of it without consent?; Was the laptop sold, converted, or simply delayed, and was there any intent to take it dishonestly?"}]}`
- Extra `BNS_316` — The repair shop is entrusted with the laptop and has not returned it one day after the estimated date, indicating possible dishonest use or conversion of the property.
- Missing uncertainty target: `BNS_316`

### SRB1_109 — missing_information — en

A product I paid for is late. The seller remains reachable and says it is delayed, and I have no facts showing dishonest intention at the time of payment.

- Gold outcome: `insufficient_information`
- Required: `(none)`
- Optional: `(none)`
- LoRA: `{"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}`
- Retrieved: `(none)`
- RAG v2.2: `{"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}`
- Missing uncertainty target: `BNS_318`

### SRB1_110 — missing_information — en

An account with a bank logo messaged me, but I do not know who controlled it or whether anyone pretended to be a particular person.

- Gold outcome: `insufficient_information`
- Required: `(none)`
- Optional: `(none)`
- LoRA: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"provision_id": "ITA_66D", "missing_facts": "identity_control_or_fabrication_and_attempted_deception_or_fraud"}]}`
- Retrieved: `ITA_66D, BNS_180`
- RAG v2.2: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"provision_id": "ITA_66D", "missing_facts": "Did the person pretending to be the bank use a communication device or computer resource to deceive?; Was there an intent to cheat by personation?"}]}`
- Missing uncertainty target: `BNS_319`

### SRB1_112 — missing_information — en

A message said 'you will regret this,' but it did not identify any injury to a person, reputation, or property and I do not know what was intended.

- Gold outcome: `insufficient_information`
- Required: `(none)`
- Optional: `(none)`
- LoRA: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"missing_facts": "The identity of a person or group, the threatened injury, and the context showing intent or knowledge to cause injury", "provision_id": "BNS_351"}]}`
- Retrieved: `BNS_351, BNS_314, BNS_217, BNS_356, BNS_318, BNS_303`
- RAG v2.2: `{"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}`
- Missing uncertainty target: `BNS_351`

### SRB1_117 — missing_information — en

A caller asked me to pay a fee, but I do not know whether the caller impersonated anyone or used a false identity.

- Gold outcome: `insufficient_information`
- Required: `(none)`
- Optional: `(none)`
- LoRA: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"provision_id": "BNS_319", "missing_facts": "whether the caller impersonated someone or used a false identity and cheated or induced an act"}]}`
- Retrieved: `BNS_319`
- RAG v2.2: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"provision_id": "BNS_319", "missing_facts": "Did the caller pretend to be someone else or use a false identity to induce payment?"}]}`
- Missing uncertainty target: `ITA_66D`

### SRB1_120 — missing_information — hinglish

Mera phone nahi mil raha; mujhe nahi pata kisi ne churaya, chheena, ya main kahin bhool gaya.

- Gold outcome: `insufficient_information`
- Required: `(none)`
- Optional: `(none)`
- LoRA: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"missing_facts": "Who moved or concealed the phone without consent and with dishonest intent?", "provision_id": "ITA_66B"}]}`
- Retrieved: `ITA_66B`
- RAG v2.2: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"provision_id": "ITA_66B", "missing_facts": "Did the person knowingly receive the phone with dishonest intent, knowing it was stolen?; Was there any evidence of unauthorized taking or concealment of the phone?"}]}`
- Missing uncertainty target: `BNS_303`

### SRB1_121 — missing_information — hinglish

Seller ne delivery delay bataya hai aur contact mein hai; mere paas shuru se fraud intention ka koi fact nahi hai.

- Gold outcome: `insufficient_information`
- Required: `(none)`
- Optional: `(none)`
- LoRA: `{"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}`
- Retrieved: `(none)`
- RAG v2.2: `{"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}`
- Missing uncertainty target: `BNS_318`

### SRB1_123 — missing_information — hi

एक व्यक्ति दो बार मेरे रास्ते में दिखा, पर उसने संपर्क नहीं किया और मुझे नहीं पता कि वह मेरा पीछा कर रहा था।

- Gold outcome: `insufficient_information`
- Required: `(none)`
- Optional: `(none)`
- LoRA: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"missing_facts": "Repeated following with intent to cause alarm or abduct", "provision_id": "BNS_203"}]}`
- Retrieved: `BNS_203`
- RAG v2.2: `{"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}`
- Missing uncertainty target: `BNS_78`

### SRB1_124 — missing_information — hi

मेरी वस्तु मरम्मत की दुकान पर है और वापसी में देरी हुई है, पर बेचने या हड़पने की कोई जानकारी नहीं है।

- Gold outcome: `insufficient_information`
- Required: `(none)`
- Optional: `(none)`
- LoRA: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"missing_facts": "Whether the property was stolen or converted by deception during the sale or attempted sale.", "provision_id": "BNS_303"}]}`
- Retrieved: `BNS_303`
- RAG v2.2: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"provision_id": "BNS_303", "missing_facts": "Was the property taken dishonestly without consent, or was it simply delayed in return?"}]}`
- Missing uncertainty target: `BNS_316`

### SRB1_142 — out_of_scope — hinglish

Internet plan ki speed advertisement se kam lag rahi hai, provider complaint investigate kar raha hai aur koi dishonest claim ka fact nahi hai.

- Gold outcome: `out_of_scope`
- Required: `(none)`
- Optional: `(none)`
- LoRA: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"missing_facts": "Whether the provider knowingly made a false speed claim and deceived a consumer.", "provision_id": "BNS_318"}]}`
- Retrieved: `BNS_318, BNS_323, BNS_315, BNS_246, BNS_320, BNS_314`
- RAG v2.2: `{"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": [{"provision_id": "BNS_318", "missing_facts": "Did the provider knowingly make a false claim about the speed of the internet plan?; Was there a deliberate deception to induce the consumer to pay for a service that does not match the advertisement?"}]}`


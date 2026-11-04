/* ============================================================
   Relative Pronouns — question bank
   Each item: prompt uses {{blank}} for the gap.
   answer: index into options (single / multi accept 0..n)
   For "pick the sentence" items, prompt is the full instruction.
   ============================================================ */
window.SECTIONS = [
  {
    key: "foundations",
    num: "01",
    title: "Foundations",
    desc: "Person or thing, subject or object — the four core pronouns in plain sentences."
  },
  {
    key: "who-whom",
    num: "02",
    title: "Who vs. whom",
    desc: "The he / him test, prepositions, and the constructions examiners love."
  },
  {
    key: "whose",
    num: "03",
    title: "Possession with whose",
    desc: "Whose for people and things — and the who's trap that catches everyone."
  },
  {
    key: "which-that",
    num: "04",
    title: "Which, that & commas",
    desc: "Defining and non-defining clauses, and why that never follows a comma."
  },
  {
    key: "in-use",
    num: "05",
    title: "Clauses in use",
    desc: "What, whoever, prepositions at the front, and pronouns you may drop."
  }
];

window.QUESTIONS = [
  /* ---------------- 01 · FOUNDATIONS ---------------- */
  {
    section: "foundations",
    prompt: "The woman {{blank}} teaches our biology class has just published a book.",
    options: ["who", "which", "whose", "what"],
    answer: 0,
    explain: "The referent is a <b>person</b> (“the woman”), and the pronoun is the <b>subject</b> of “teaches” — rewrite it as “<em>She</em> teaches our class”. Person + subject = <b>who</b>.",
    tip: "People take who / whom. Things take which / that."
  },
  {
    section: "foundations",
    prompt: "This is the novel {{blank}} won the Booker Prize last year.",
    options: ["who", "which", "whose", "whom"],
    answer: 1,
    explain: "A novel is a <b>thing</b>, and it is the <b>subject</b> of “won”: “<em>it</em> won the prize”. Thing + subject = <b>which</b> (or <b>that</b>).",
    tip: "Which and that are interchangeable in defining clauses about things."
  },
  {
    section: "foundations",
    prompt: "I have a neighbour {{blank}} dog barks all night.",
    options: ["who's", "whose", "which", "whom"],
    answer: 1,
    explain: "We are talking about the <b>possessor</b> of the dog, so we need the possessive <b>whose</b>. Test it: “<em>his</em> dog” works, so “whose dog” is right. “Who’s” only ever means “who is” or “who has”.",
    tip: "If you can replace it with his / her / its, write whose."
  },
  {
    section: "foundations",
    prompt: "{{blank}} you told me yesterday turned out to be true.",
    options: ["That", "What", "Which", "It"],
    answer: 1,
    explain: "There is <b>no noun before the pronoun</b> for it to refer to, so we need <b>what</b> = “the thing(s) that”. “What you told me” is the whole subject of the sentence.",
    tip: "Write “the thing that” or “what” — never “the thing what”."
  },
  {
    section: "foundations",
    prompt: "Choose every pronoun that correctly completes the sentence: “The film {{blank}} we watched last night was three hours long.”",
    options: ["which", "that", "who", "whose", "whom"],
    answer: [0, 1],
    explain: "The film is a <b>thing</b> and the pronoun is the <b>object</b> of “watched” (“we watched <em>it</em>”). Both <b>which</b> and <b>that</b> are correct — and because it is an object, you could even leave it out: “The film we watched…”. <b>Who</b> and <b>whom</b> need people; <b>whose</b> needs possession.",
    tip: "In a defining clause about a thing, which and that are both fine."
  },
  {
    section: "foundations",
    prompt: "The city {{blank}} I was born has changed beyond recognition.",
    options: ["which", "where", "that", "when"],
    answer: 1,
    explain: "We need a relative <b>adverb</b> of place: <b>where</b> = “in which”. “The city which I was born” is wrong because <em>which</em> would have to be the object of a missing preposition. “The city in which I was born” is the formal alternative.",
    tip: "Place with no preposition → where (or in / at which)."
  },
  {
    section: "foundations",
    prompt: "All {{blank}} she wanted was a quiet evening at home.",
    options: ["which", "that", "what", "who"],
    answer: 1,
    explain: "After <b>all, everything, nothing, anything, the only, the best</b>, English strongly prefers <b>that</b>. “All which she wanted” is not used, and “All what” is impossible because <em>what</em> already contains its noun.",
    tip: "All / everything / nothing / the only → that."
  },
  {
    section: "foundations",
    prompt: "The letter, {{blank}} arrived this morning, was addressed to my father.",
    options: ["that", "which", "who", "what"],
    answer: 1,
    explain: "The commas make this a <b>non-defining</b> clause — extra information. In that kind of clause <b>that is never possible</b>; for a thing you must use <b>which</b>. A letter is also a thing, so <em>who</em> is out.",
    tip: "Comma clause about a thing → which. Never that."
  },

  /* ---------------- 02 · WHO vs WHOM ---------------- */
  {
    section: "who-whom",
    prompt: "The consultant {{blank}} we hired last month has already saved the company a fortune.",
    options: ["who", "whom", "which", "whose"],
    answer: 1,
    explain: "The pronoun is the <b>object</b> of “hired”: we hired <em>him</em>. Object + person = <b>whom</b>. (In relaxed speech “who” is common here, but exams expect <em>whom</em>.)",
    tip: "he → who · him → whom."
  },
  {
    section: "who-whom",
    prompt: "The professor with {{blank}} I studied economics retired last year.",
    options: ["who", "whom", "whose", "which"],
    answer: 1,
    explain: "After a <b>preposition</b> (“with”), the object form <b>whom</b> is required. “With who” is wrong even in informal English.",
    tip: "Preposition + person → always whom."
  },
  {
    section: "who-whom",
    prompt: "The applicants, most of {{blank}} had no experience, were still interviewed.",
    options: ["who", "whom", "which", "whose"],
    answer: 1,
    explain: "Quantifier + <b>of</b> + relative pronoun, referring to people: “most of <em>them</em>” → <b>whom</b>. If the pronoun is governed by a preposition like this, the object form is compulsory.",
    tip: "Most of / some of / none of + whom."
  },
  {
    section: "who-whom",
    prompt: "It was my brother {{blank}} broke the window, not me.",
    options: ["who", "whom", "which", "whose"],
    answer: 0,
    explain: "This is a cleft sentence (“It was X <em>who</em> …”). The pronoun is the <b>subject</b> of “broke”: <em>he</em> broke the window → <b>who</b>.",
    tip: "he broke it → who · I saw him → whom."
  },
  {
    section: "who-whom",
    prompt: "The candidate {{blank}} the committee selected was not the favourite.",
    options: ["who", "whom", "whose", "which"],
    answer: 1,
    explain: "The committee selected <em>him</em>: the pronoun is the <b>object</b> of “selected”, so the formal choice is <b>whom</b>.",
    tip: "Ask: who did the selecting? The committee. So the relative pronoun is the object."
  },
  {
    section: "who-whom",
    prompt: "Which sentence uses the relative pronoun most appropriately in formal writing?",
    options: [
      "The witness who the police questioned gave a detailed statement.",
      "The witness whom the police questioned gave a detailed statement.",
      "The witness whom questioned the police gave a detailed statement.",
      "The witness which the police questioned gave a detailed statement."
    ],
    answer: 1,
    explain: "The police questioned <em>him</em>, so the clause needs the object form <b>whom</b>. Option A uses <em>who</em>, which is tolerated in speech but not in formal writing; option C makes <em>whom</em> the subject, which is impossible; option D uses <em>which</em> for a person.",
    tip: "Only wh- pronouns ending in -m can be objects."
  },

  /* ---------------- 03 · WHOSE ---------------- */
  {
    section: "whose",
    prompt: "We met a girl {{blank}} parents own the bakery on the corner.",
    options: ["who's", "whose", "which", "whom"],
    answer: 1,
    explain: "<b>Whose</b> shows possession: “<em>her</em> parents”. <b>Who’s</b> is a contraction of “who is” or “who has”, so “who’s parents own…” would mean “who is parents own”, which is impossible.",
    tip: "whose + noun · who’s + verb."
  },
  {
    section: "whose",
    prompt: "The building {{blank}} windows face the river is the oldest in town.",
    options: ["who's", "whose", "which's", "that's"],
    answer: 1,
    explain: "<b>Whose</b> works for <b>things</b> as well as people — it means “of which”. “<b>Which’s</b>” is not a word in English, and “who’s” / “that’s” are contractions, not possessives.",
    tip: "A thing can possess something: the building whose windows…"
  },
  {
    section: "whose",
    prompt: "Which sentence is written correctly?",
    options: [
      "The author who's first novel won a prize lives in Dublin.",
      "The author whose first novel won a prize lives in Dublin.",
      "The author which first novel won a prize lives in Dublin.",
      "The author who first novel won a prize lives in Dublin."
    ],
    answer: 1,
    explain: "We need the possessive form before the noun phrase “first novel”: <b>whose</b>. “Who’s” = who is / who has; “which” cannot show possession; bare “who” cannot stand before a noun like that.",
    tip: "Substitute his: “his first novel” → whose."
  },
  {
    section: "whose",
    prompt: "The team {{blank}} captain resigned lost three matches in a row.",
    options: ["whose", "who's", "which", "who"],
    answer: 0,
    explain: "The captain belongs to the team, so the pronoun must be possessive: <b>whose</b>. Note that <em>whose</em> is the only relative possessive in English — there is no “which’s”.",
    tip: "Whose + noun is the only possessive relative construction."
  },
  {
    section: "whose",
    prompt: "Which sentence is INCORRECT?",
    options: [
      "The writer whose books I love is giving a talk tonight.",
      "The writer whose I love his books is giving a talk tonight.",
      "A country whose economy is growing attracts investors.",
      "The dog whose collar was red belongs to my neighbour."
    ],
    answer: 1,
    explain: "Option 2 is wrong because <b>whose</b> already contains the possessive idea — adding “his” doubles it. It should be “the writer <b>whose</b> books I love”. The other three use <em>whose</em> correctly, including for a country and a dog.",
    tip: "Never write whose … his / her / its in the same clause."
  },

  /* ---------------- 04 · WHICH, THAT & COMMAS ---------------- */
  {
    section: "which-that",
    prompt: "My laptop, {{blank}} I bought only two years ago, has stopped working.",
    options: ["that", "which", "who", "what"],
    answer: 1,
    explain: "The clause is between commas — <b>non-defining</b>. Here <b>that</b> is ungrammatical; use <b>which</b> for a thing. The clause only adds extra information; it does not identify the laptop.",
    tip: "Non-defining clause → which, never that."
  },
  {
    section: "which-that",
    prompt: "Choose every pronoun that correctly completes the sentence: “The report {{blank}} she submitted at midnight contained three errors.”",
    options: ["which", "that", "who", "whose"],
    answer: [0, 1],
    explain: "No commas, and the report is a thing, so both <b>which</b> and <b>that</b> are correct. Because the pronoun is the object of “submitted”, you could also omit it: “The report she submitted…”.",
    tip: "Defining + thing + object → which / that / (nothing)."
  },
  {
    section: "which-that",
    prompt: "He arrived an hour late, {{blank}} made everyone furious.",
    options: ["that", "which", "what", "who"],
    answer: 1,
    explain: "Here the pronoun refers to the <b>whole previous clause</b> (“he arrived an hour late”), not to a noun. Only <b>which</b> can do that. <b>That</b> must refer to a noun, and <b>what</b> cannot follow a comma like this.",
    tip: "Commenting on a whole idea → , which …"
  },
  {
    section: "which-that",
    prompt: "My sister, {{blank}} lives in Berlin, is visiting next week.",
    options: ["who", "that", "which", "whom"],
    answer: 0,
    explain: "A person as the <b>subject</b> of “lives” takes <b>who</b>. The commas make it non-defining, which rules out <b>that</b>; <b>which</b> is for things and <b>whom</b> is an object form.",
    tip: "Comma clause about a person → who / whom, never that."
  },
  {
    section: "which-that",
    prompt: "The company, {{blank}} employs two thousand people, is moving its headquarters abroad.",
    options: ["who", "which", "whose", "whom"],
    answer: 1,
    explain: "Companies and organisations are treated as <b>things</b> in formal English, so a non-defining clause takes <b>which</b> — not <em>who</em>. <em>Whose</em> would need a following noun (“whose staff…”).",
    tip: "A company / government / team = it → which."
  },
  {
    section: "which-that",
    prompt: "Which sentence is INCORRECT?",
    options: [
      "The car that I bought last year is electric.",
      "The car, that I bought last year, is electric.",
      "The car which I bought last year is electric.",
      "The car I bought last year is electric."
    ],
    answer: 1,
    explain: "Option 2 is wrong twice over: <b>that</b> cannot appear in a comma clause, and the object pronoun here can simply be dropped. The other three are all correct — note that option 4 omits the pronoun altogether, which is allowed because it is the object of “bought”.",
    tip: "That has two enemies: commas and prepositions."
  },
  {
    section: "which-that",
    prompt: "That is the reason {{blank}} she refused the offer.",
    options: ["why", "which", "what", "whose"],
    answer: 0,
    explain: "For reason we use the relative adverb <b>why</b> (= “for which”): “the reason <b>why</b> she refused”. <em>Which</em> alone cannot replace it here, and <em>what</em> / <em>whose</em> do not fit at all.",
    tip: "the reason why · the place where · the day when."
  },

  /* ---------------- 05 · CLAUSES IN USE ---------------- */
  {
    section: "in-use",
    prompt: "{{blank}} surprised me most was her calm reaction.",
    options: ["That", "What", "Which", "It"],
    answer: 1,
    explain: "There is no noun for the pronoun to describe, and the clause is the subject of “surprised”: <b>What</b> = “the thing that”. “That surprised me most was…” is ungrammatical because <em>that</em> needs a noun in front of it.",
    tip: "The thing that = what (never that on its own at the start)."
  },
  {
    section: "in-use",
    prompt: "In which sentence can the relative pronoun be left out?",
    options: [
      "The book which is on the table is mine.",
      "The book which she bought is mine.",
      "The man who lives next door is a chef.",
      "The letter that arrived today is for you."
    ],
    answer: 1,
    explain: "You may omit the relative pronoun <b>only when it is the object</b> of the clause: “The book she bought is mine.” In options 1, 3 and 4 the pronoun is the <b>subject</b> (“which <em>is</em>”, “who <em>lives</em>”, “that <em>arrived</em>”), so it must stay.",
    tip: "Subject → keep it. Object → you may drop it."
  },
  {
    section: "in-use",
    prompt: "The tool {{blank}} he fixed the car was borrowed from a neighbour.",
    options: ["with which", "which", "that", "with that"],
    answer: 0,
    explain: "“Fix the car <b>with</b> a tool” — the preposition belongs with the verb, so in this formal order it comes before the pronoun: <b>with which</b>. <b>That</b> can never follow a preposition, and bare <em>which</em> would leave the preposition dangling mid-clause.",
    tip: "Preposition + which · never preposition + that."
  },
  {
    section: "in-use",
    prompt: "{{blank}} finishes first will win a free course.",
    options: ["Whomever", "Whoever", "Who", "Whose"],
    answer: 1,
    explain: "<b>Whoever</b> means “the person who” and here it is the <b>subject</b> of “finishes”, so it takes the -ever subject form. <em>Whomever</em> would be an object, and “Who finishes first will win” needs a different structure (“The person who finishes first…”).",
    tip: "-ever forms follow the same subject / object logic."
  },
  {
    section: "in-use",
    prompt: "Which sentence is INCORRECT?",
    options: [
      "What she said was true.",
      "The thing what she said was true.",
      "The thing that she said was true.",
      "Everything that she said was true."
    ],
    answer: 1,
    explain: "Option 2 uses <b>two</b> relative words — “the thing” already supplies the noun, so <em>what</em> is impossible. Use either “<b>What</b> she said…” or “<b>The thing that</b> she said…”. Options 1, 3 and 4 are all correct.",
    tip: "what = the thing that. Never “the thing what”."
  },
  {
    section: "in-use",
    prompt: "The year {{blank}} we moved to Jakarta was unusually wet.",
    options: ["when", "which", "what", "whose"],
    answer: 0,
    explain: "For time we use the relative adverb <b>when</b> (= “in which”): “the year <b>when</b> we moved”. <em>Which</em> alone would need a preposition (“the year <b>in which</b>”), and <em>what</em> / <em>whose</em> do not fit.",
    tip: "the year when · the day when · the moment when."
  }
];

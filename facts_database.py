"""
facts_database.py — Baza unikalnych ciekawostek psychologicznych
================================================================
Dostarcza 3 różne, niewykorzystane jeszcze fakty do każdego shorta.
Fakty są pogrupowane w 8 kategoriach — rotacja kategorii zapobiega
content fatigue (każdy short = inna sub-nisza).

Użycie:
    from facts_database import FactSelector
    facts = FactSelector().select_for_video(video_index=1, profile="dark_mindset")
    # → lista 3 dictów: {id, category, fact, hook_angle}
"""

import os
import json
from datetime import datetime, timezone
from typing import List, Dict

USED_FACTS_FILE = os.path.join("accounts", "used_facts.json")

# ──────────────────────────────────────────────────────────────────────────────
# BAZA FAKTÓW — 120+ unikalnych, skatalogowanych ciekawostek psychologicznych
# Każdy fakt: {id, category, fact, hook_angle}
# hook_angle = propozycja skrętnego ujęcia dla AI
# ──────────────────────────────────────────────────────────────────────────────
FACTS_DB: List[Dict] = [

    # ═════════════════════════════════════════════════════
    # KATEGORIA 1: MOWA CIAŁA & MIKROWYRAZY
    # ═════════════════════════════════════════════════════
    {
        "id": "bl_001",
        "category": "body_language",
        "fact": "The 'steeple' hand gesture — fingertips pressed together like a church spire — signals extreme confidence. FBI profiler Joe Navarro documented it as the single most reliable indicator of someone who feels dominant in the room.",
        "hook_angle": "The hand gesture that reveals who actually controls the conversation"
    },
    {
        "id": "bl_002",
        "category": "body_language",
        "fact": "Rubbing the back of the neck while speaking is a 'pacifying behavior' — the brain triggers it to self-soothe during psychological discomfort. Navarro identified it as one of the most reliable tells for hidden stress or deception.",
        "hook_angle": "Why people touch their neck when they're lying to you"
    },
    {
        "id": "bl_003",
        "category": "body_language",
        "fact": "A genuine Duchenne smile contracts the orbicularis oculi muscle around the eye corners. This muscle cannot be voluntarily controlled — meaning anyone who smiles without eye crinkles is performing, not feeling.",
        "hook_angle": "The one muscle that exposes every fake smile instantly"
    },
    {
        "id": "bl_004",
        "category": "body_language",
        "fact": "Power poses literally change brain chemistry — holding a dominant posture for just 2 minutes increases testosterone by 20% and lowers cortisol by 25%, before you say a single word (Carney, Cuddy, Yap — Harvard).",
        "hook_angle": "2 minutes that chemically rewire your confidence before any interaction"
    },
    {
        "id": "bl_005",
        "category": "body_language",
        "fact": "People who feel threatened unconsciously mirror the posture of whoever they fear — not as respect, but as a survival mechanism to appear similar and avoid conflict.",
        "hook_angle": "Why you start copying the body language of people who intimidate you"
    },
    {
        "id": "bl_006",
        "category": "body_language",
        "fact": "Dilated pupils signal genuine interest or attraction — and cannot be faked or suppressed voluntarily. This is why casinos use dim lighting; it dilates pupils and makes players appear more interested in each other.",
        "hook_angle": "The pupil signal that betrays genuine attraction before any words are spoken"
    },
    {
        "id": "bl_007",
        "category": "body_language",
        "fact": "Looking up-right when recalling something indicates visual construction (imagination), while looking up-left signals visual memory. This distinction, used in NLP profiling, can reveal whether someone is inventing or remembering.",
        "hook_angle": "The eye direction that reveals if someone is lying or remembering"
    },
    {
        "id": "bl_008",
        "category": "body_language",
        "fact": "When someone points their feet toward you during a conversation, they're genuinely engaged. When they point feet toward the exit while still talking to you, their unconscious mind has already left.",
        "hook_angle": "The foot signal that shows someone wants to escape the conversation"
    },
    {
        "id": "bl_009",
        "category": "body_language",
        "fact": "Crossed arms are not always a sign of defensiveness — research by Geoffrey Beattie (Manchester) showed crossed arms correlate with concentration and comfort when the person initiated the posture themselves.",
        "hook_angle": "Why misreading crossed arms is one of the most common social mistakes"
    },
    {
        "id": "bl_010",
        "category": "body_language",
        "fact": "Speed of blinking increases under stress — baseline is 6-8 blinks/minute, but under psychological pressure this can spike to 50+. Politicians are specifically trained to maintain low blink rates during interviews.",
        "hook_angle": "The blinking rate politicians are trained to control"
    },

    # ═════════════════════════════════════════════════════
    # KATEGORIA 2: BŁĘDY POZNAWCZE & PODEJMOWANIE DECYZJI
    # ═════════════════════════════════════════════════════
    {
        "id": "cb_001",
        "category": "cognitive_bias",
        "fact": "The Pratfall Effect (Aronson, 1966): People who appear highly competent become significantly MORE likable after making a small mistake. Perfection creates distance; visible vulnerability creates connection.",
        "hook_angle": "Why making a mistake in front of someone makes them trust you more"
    },
    {
        "id": "cb_002",
        "category": "cognitive_bias",
        "fact": "The Peak-End Rule (Kahneman): You don't remember experiences as averages — you remember only the most intense moment and the final moment. Dentists who end appointments with neutral small talk are genuinely rated as less painful.",
        "hook_angle": "Why only 2 moments of any experience actually matter to your brain"
    },
    {
        "id": "cb_003",
        "category": "cognitive_bias",
        "fact": "Effort Justification (Festinger): The harder someone worked for something, the more they value it — even if it's objectively worthless. Hazing rituals, expensive restaurants, and cults all exploit this exact mechanism.",
        "hook_angle": "Why suffering to get something makes you value it more, not less"
    },
    {
        "id": "cb_004",
        "category": "cognitive_bias",
        "fact": "The Mere Exposure Effect (Zajonc, 1968): Simply being exposed to something repeatedly increases liking for it — with no interaction required. Familiarity is chemically indistinguishable from trust in the primitive brain.",
        "hook_angle": "Why you trust faces you've seen before without ever meeting them"
    },
    {
        "id": "cb_005",
        "category": "cognitive_bias",
        "fact": "Illusion of Asymmetric Insight (Pronin, 2001): We believe we understand other people better than they understand us — but research shows we know far less about ourselves than others do. Your 'hidden self' is visible to everyone but you.",
        "hook_angle": "The bias that makes you think you understand people who see right through you"
    },
    {
        "id": "cb_006",
        "category": "cognitive_bias",
        "fact": "The Spotlight Effect (Gilovich): People dramatically overestimate how much others notice their mistakes. In studies, participants wearing embarrassing shirts estimated 50% of people would notice — the actual number was under 25%.",
        "hook_angle": "Why nobody is watching you as closely as you think they are"
    },
    {
        "id": "cb_007",
        "category": "cognitive_bias",
        "fact": "Anchoring Bias: The first number heard in any negotiation becomes a psychological anchor that all subsequent judgments are compared to — regardless of its accuracy or relevance. This cannot be bypassed by knowing it exists.",
        "hook_angle": "The number trick used in every negotiation that your brain can't escape"
    },
    {
        "id": "cb_008",
        "category": "cognitive_bias",
        "fact": "Sunk Cost Fallacy: The brain physically cannot emotionally disconnect past investment from future decisions — causing people to continue failing projects, toxic relationships, and losing bets purely because they've already committed.",
        "hook_angle": "Why knowing about the sunk cost fallacy doesn't stop you from falling for it"
    },
    {
        "id": "cb_009",
        "category": "cognitive_bias",
        "fact": "The Dunning-Kruger Effect inverts at high competence levels — true experts often underestimate their knowledge because they're surrounded by other experts. The least skilled are most confident; the most skilled are most doubtful.",
        "hook_angle": "Why the most confident person in the room is rarely the most competent"
    },
    {
        "id": "cb_010",
        "category": "cognitive_bias",
        "fact": "Confirmation Bias: Once you believe something, your brain unconsciously filters all new information to confirm it — treating contradictory evidence as irrelevant and supportive evidence as definitive proof.",
        "hook_angle": "Why once you've decided someone is bad, you can't see anything good in them"
    },
    {
        "id": "cb_011",
        "category": "cognitive_bias",
        "fact": "The Zeigarnik Effect: Incomplete tasks are remembered 90% better than completed ones — because the brain keeps them in active working memory. This is why cliffhangers, unfinished sentences, and open loops are psychologically irresistible.",
        "hook_angle": "Why your brain won't let you forget things you never finished"
    },
    {
        "id": "cb_012",
        "category": "cognitive_bias",
        "fact": "Choice Overload (Schwartz 'Paradox of Choice'): More options lead to less satisfaction with the final choice and greater likelihood of choosing nothing. Limiting options to 3-4 increases both decision rate and happiness with the outcome.",
        "hook_angle": "Why having fewer choices makes you happier with what you pick"
    },

    # ═════════════════════════════════════════════════════
    # KATEGORIA 3: DARK TRIAD & MANIPULACJA
    # ═════════════════════════════════════════════════════
    {
        "id": "dt_001",
        "category": "dark_triad",
        "fact": "Narcissists specifically target empaths — not randomly. Empaths' tendency to over-explain, self-blame, and absorb others' emotions makes them ideal sources of 'narcissistic supply': emotional energy to feed the narcissist's ego.",
        "hook_angle": "Why narcissists always seem to find the most empathetic people"
    },
    {
        "id": "dt_002",
        "category": "dark_triad",
        "fact": "The Gray Rock Method: Psychologists advise becoming boring around narcissists — giving only flat, factual, non-emotional responses. Without emotional reaction to feed on, narcissists lose interest and naturally disengage.",
        "hook_angle": "The psychological trick that makes toxic people stop targeting you"
    },
    {
        "id": "dt_003",
        "category": "dark_triad",
        "fact": "Psychopaths have measurably smaller amygdalae and reduced amygdala activation when viewing others' fear — they literally don't register fear cues the same way, explaining their absence of empathy. This is neurological, not chosen.",
        "hook_angle": "The brain structure difference that makes someone incapable of empathy"
    },
    {
        "id": "dt_004",
        "category": "dark_triad",
        "fact": "Machiavellians outperform narcissists in long-term manipulation because they control their ego — they can compliment rivals, delay gratification, and appear trustworthy for years before revealing their agenda.",
        "hook_angle": "The personality type that manipulates you for years before you notice"
    },
    {
        "id": "dt_005",
        "category": "dark_triad",
        "fact": "Gaslighting works by exploiting memory's reconstructive nature — each time you recall a memory, you slightly rewrite it. Consistent reality distortion by an abuser gradually overwrites the victim's original memory with the abuser's version.",
        "hook_angle": "Why gaslighting actually works — it physically rewrites your memories"
    },
    {
        "id": "dt_006",
        "category": "dark_triad",
        "fact": "Triangulation: Narcissists deliberately introduce a third person (real or implied) to create insecurity and competition. The victim's jealousy response confirms attachment and gives the narcissist control leverage.",
        "hook_angle": "Why toxic people always seem to mention someone else to make you jealous"
    },
    {
        "id": "dt_007",
        "category": "dark_triad",
        "fact": "Love bombing — overwhelming a new partner with intense attention and affection — creates a neurochemical baseline. When the attention later disappears, the victim chases the original dopamine high, not the person.",
        "hook_angle": "Why you miss the person who treated you worst — the neuroscience of love bombing"
    },
    {
        "id": "dt_008",
        "category": "dark_triad",
        "fact": "Covert narcissists are harder to detect than overt types — they present as victims, humble, and self-deprecating, using vulnerability as a weapon to receive sympathy and manipulate through guilt.",
        "hook_angle": "The type of narcissist you never recognize until it's too late"
    },
    {
        "id": "dt_009",
        "category": "dark_triad",
        "fact": "The DARVO tactic (Deny, Attack, Reverse Victim and Offender) — when confronted, manipulators deny the behavior, attack the accuser, and position themselves as the real victim. Studies show it's used by 85% of narcissists when confronted.",
        "hook_angle": "The 3-step script every manipulator uses when you call them out"
    },
    {
        "id": "dt_010",
        "category": "dark_triad",
        "fact": "Flying Monkeys — narcissists recruit proxy people who do their manipulation by proxy, often without knowing they're being used. The narcissist controls through the network while maintaining 'clean hands.'",
        "hook_angle": "How toxic people use your mutual friends to control you without being there"
    },

    # ═════════════════════════════════════════════════════
    # KATEGORIA 4: WYWIERANIE WPŁYWU & PERSWAZJA
    # ═════════════════════════════════════════════════════
    {
        "id": "si_001",
        "category": "social_influence",
        "fact": "Door-in-the-Face technique: Asking for something enormous first — then following with the real, smaller request — makes compliance 3x more likely than asking directly. The brain interprets the smaller request as a generous concession.",
        "hook_angle": "The request trick that makes people agree to almost anything"
    },
    {
        "id": "si_002",
        "category": "social_influence",
        "fact": "Foot-in-the-Door technique (Freedman & Fraser, 1966): Getting a tiny 'yes' first — like signing a petition — makes people 400% more likely to comply with a much larger request two weeks later, because they've established a consistent self-image.",
        "hook_angle": "Why agreeing to something small makes you agree to much bigger things"
    },
    {
        "id": "si_003",
        "category": "social_influence",
        "fact": "Milgram's Obedience Study: 65% of ordinary people delivered what they believed were lethal electric shocks to strangers — purely because an authority figure in a white coat told them to continue. Authority overrides personal morality.",
        "hook_angle": "The experiment that proved most people will hurt others on command"
    },
    {
        "id": "si_004",
        "category": "social_influence",
        "fact": "Reciprocity is the most powerful influence principle (Cialdini): Receiving any gift — even an unwanted one — creates a psychological debt that the brain desperately wants to eliminate through compliance.",
        "hook_angle": "Why getting a free gift makes you feel like you owe someone something"
    },
    {
        "id": "si_005",
        "category": "social_influence",
        "fact": "Scarcity Principle: Items become more desirable not because of inherent value, but because of perceived unavailability. 'Limited edition' labels increase purchase intent by 47% for identical products.",
        "hook_angle": "Why 'limited edition' makes you want something you didn't care about before"
    },
    {
        "id": "si_006",
        "category": "social_influence",
        "fact": "Tactical mirroring (FBI negotiator Chris Voss): Repeating the last 1-3 words someone said as a question — with downward inflection — creates an instant rapport response, causing them to reveal far more than intended.",
        "hook_angle": "The FBI interrogation technique that makes people reveal their secrets"
    },
    {
        "id": "si_007",
        "category": "social_influence",
        "fact": "The Benjamin Franklin Effect: Asking someone to do a small favor for you — not doing one for them — makes them like you more. The brain resolves the cognitive dissonance of 'I did them a favor, so I must like them.'",
        "hook_angle": "Why asking someone for a favor makes them like you more than helping them"
    },
    {
        "id": "si_008",
        "category": "social_influence",
        "fact": "Social Proof is most powerful in ambiguous situations — when uncertain, people look to others for behavioral cues, even if those others are equally confused. 'Everyone else is doing it' overrides individual judgment.",
        "hook_angle": "Why crowds of confused people confidently follow other confused people"
    },
    {
        "id": "si_009",
        "category": "social_influence",
        "fact": "The 'Labeling' technique (Cialdini): Assigning a positive trait to someone ('You seem like someone who values honesty') significantly increases the likelihood they'll behave in line with that label. People conform to assigned identities.",
        "hook_angle": "Why calling someone honest before asking a question makes them more honest"
    },
    {
        "id": "si_010",
        "category": "social_influence",
        "fact": "Strategic self-deprecation increases perceived competence — when experts preemptively acknowledge a weakness before making their case, they're rated as more trustworthy and their arguments are more persuasive.",
        "hook_angle": "Why admitting your weakness before presenting your argument makes it stronger"
    },

    # ═════════════════════════════════════════════════════
    # KATEGORIA 5: NEUROPSYCHOLOGIA & MÓZG
    # ═════════════════════════════════════════════════════
    {
        "id": "np_001",
        "category": "neuropsychology",
        "fact": "Dopamine is not released when you get a reward — it's released in anticipation of a possible reward. Unpredictable reward schedules (slot machines, social media, hot-and-cold people) are chemically more addictive than consistent ones.",
        "hook_angle": "Why your brain is more addicted to maybe than to yes"
    },
    {
        "id": "np_002",
        "category": "neuropsychology",
        "fact": "The brain cannot distinguish between physical pain and social rejection — the anterior cingulate cortex activates identically for both. Being excluded from a group literally causes the same pain response as physical injury.",
        "hook_angle": "Why social rejection activates the same brain region as being physically hurt"
    },
    {
        "id": "np_003",
        "category": "neuropsychology",
        "fact": "Emotional contagion: Humans unconsciously mirror facial expressions within 0.3 seconds of seeing them — which induces the actual underlying emotion. You can literally transmit your emotional state to others without speaking.",
        "hook_angle": "Why spending time with anxious people makes you anxious without knowing why"
    },
    {
        "id": "np_004",
        "category": "neuropsychology",
        "fact": "Decision fatigue: The quality of human decisions deteriorates significantly after making many decisions. Judges grant parole 65% of the time at the start of the day — dropping to nearly 0% before lunch, then resetting after a break.",
        "hook_angle": "Why judges make worst decisions before lunch — and what this means for your life"
    },
    {
        "id": "np_005",
        "category": "neuropsychology",
        "fact": "The amygdala processes threat responses in 12-14 milliseconds — before conscious awareness — meaning your body is already in fight-or-flight before you can think about whether something is dangerous.",
        "hook_angle": "Your body reacts to danger before your conscious mind even knows about it"
    },
    {
        "id": "np_006",
        "category": "neuropsychology",
        "fact": "Memory is reconstructive, not reproductive — every time you recall a memory, you slightly rewrite it based on your current emotional state. The version you remember now is not what actually happened.",
        "hook_angle": "Every time you remember something, you're rewriting what actually happened"
    },
    {
        "id": "np_007",
        "category": "neuropsychology",
        "fact": "The brain burns more energy avoiding loss than pursuing equivalent gain — 'loss aversion' makes losing $100 feel twice as bad as gaining $100 feels good, making fear-based motivation more powerful than reward-based.",
        "hook_angle": "Why the fear of losing motivates you twice as much as the chance of winning"
    },
    {
        "id": "np_008",
        "category": "neuropsychology",
        "fact": "Mirror neurons fire both when you perform an action AND when you observe someone else performing it — meaning watching someone suffer activates pain circuitry in your own brain. Empathy is neurologically automatic.",
        "hook_angle": "The neurons that make you physically feel what you watch others experience"
    },
    {
        "id": "np_009",
        "category": "neuropsychology",
        "fact": "Sleep deprivation after 24 hours produces cognitive impairment equivalent to 0.1% blood alcohol content — legally drunk — while the sleep-deprived person rates their own performance as unimpaired.",
        "hook_angle": "After one sleepless night your brain works like you're legally drunk"
    },
    {
        "id": "np_010",
        "category": "neuropsychology",
        "fact": "The brain defaults to narrative — it cannot process raw data without creating a story. This is why conspiracy theories spread faster than statistics; the narrative structure matches the brain's default processing mode.",
        "hook_angle": "Why your brain prefers a good story over actual facts every single time"
    },

    # ═════════════════════════════════════════════════════
    # KATEGORIA 6: DYNAMIKA WŁADZY & DOMINACJA
    # ═════════════════════════════════════════════════════
    {
        "id": "pw_001",
        "category": "power_dynamics",
        "fact": "People who speak slower are consistently rated as more powerful, confident, and intelligent — regardless of what they're saying. Fast speaking signals anxiety; slow speaking signals control. Speed is a power signal.",
        "hook_angle": "How fast you talk tells everyone in the room how scared you are"
    },
    {
        "id": "pw_002",
        "category": "power_dynamics",
        "fact": "Strategic Incompetence: Powerful people often pretend not to know how to do low-status tasks, causing others to take over. It's a deliberate power play that maintains status while shifting work downward.",
        "hook_angle": "Why powerful people pretend not to know things they understand perfectly"
    },
    {
        "id": "pw_003",
        "category": "power_dynamics",
        "fact": "In negotiations, the first person to speak after a proposal fills the silence from discomfort — and almost always makes a concession. Silence signals absolute confidence that the offer stands. Silence is the most powerful negotiating move.",
        "hook_angle": "The negotiation move worth more than any word you could say"
    },
    {
        "id": "pw_004",
        "category": "power_dynamics",
        "fact": "The person asking questions in a conversation is perceived as more intelligent AND ends up knowing more while revealing less. Powerful interrogators ask; powerless people explain.",
        "hook_angle": "Why the smartest people in the room ask questions instead of answering them"
    },
    {
        "id": "pw_005",
        "category": "power_dynamics",
        "fact": "Status is signaled by how late you arrive — people with perceived high status are granted 'latitude credit,' meaning their lateness is excused while others' isn't. Punctuality signals eagerness; lateness signals demand.",
        "hook_angle": "The social hierarchy signal hidden in when people arrive"
    },
    {
        "id": "pw_006",
        "category": "power_dynamics",
        "fact": "The 'Cold Shoulder' technique — withdrawing attention without explanation — exploits the human need for social connection. Silence and absence are more psychologically controlling than any direct confrontation.",
        "hook_angle": "Why ignoring someone gives you more power over them than fighting with them"
    },
    {
        "id": "pw_007",
        "category": "power_dynamics",
        "fact": "High-status individuals use fewer words to communicate more — they eliminate hedging language ('I think maybe...', 'sort of...'). Verbal hedging signals low confidence; declarative statements signal authority.",
        "hook_angle": "The speech habit that immediately signals low status to everyone listening"
    },
    {
        "id": "pw_008",
        "category": "power_dynamics",
        "fact": "Who breaks eye contact first in a face-to-face encounter typically has lower status — the dominant individual maintains gaze while the submissive one looks away. Eye contact duration is a direct status display.",
        "hook_angle": "Breaking eye contact first reveals exactly where you rank in any room"
    },

    # ═════════════════════════════════════════════════════
    # KATEGORIA 7: PRZYWIĄZANIE & RELACJE
    # ═════════════════════════════════════════════════════
    {
        "id": "ar_001",
        "category": "attachment",
        "fact": "Intermittent reinforcement (hot-and-cold behavior) is the most addictive behavioral pattern in psychology — more addictive than consistent reward. The unpredictability spikes dopamine in anticipation, creating compulsive attachment.",
        "hook_angle": "Why the person who treats you worst is the one you can't stop thinking about"
    },
    {
        "id": "ar_002",
        "category": "attachment",
        "fact": "Anxious attachment style individuals respond with greater emotional intensity to inconsistent partners — the uncertainty activates the threat response, which the brain misinterprets as passion and 'chemistry.'",
        "hook_angle": "Why anxiety about someone is so easily confused for being in love with them"
    },
    {
        "id": "ar_003",
        "category": "attachment",
        "fact": "Avoidant attachment individuals push people away not from lack of feeling, but from fear of dependency — they become most emotionally activated when a partner stops pursuing, because distance feels safe.",
        "hook_angle": "Why emotionally unavailable people suddenly want you the moment you pull away"
    },
    {
        "id": "ar_004",
        "category": "attachment",
        "fact": "The 'Closeness-Communication Bias' (Savitsky, 2011): We communicate less clearly with people we're closest to — assuming shared context — while putting more effort into clarity with strangers. Familiarity breeds miscommunication.",
        "hook_angle": "Why the people you know best misunderstand you the most"
    },
    {
        "id": "ar_005",
        "category": "attachment",
        "fact": "Trauma bonding creates neurological attachment to abusers — cycles of tension, abuse, and reconciliation release identical neurochemicals (cortisol spike followed by oxytocin release) as extreme bonding experiences.",
        "hook_angle": "The neurochemical cycle that bonds you to people who hurt you"
    },
    {
        "id": "ar_006",
        "category": "attachment",
        "fact": "The mere act of disclosing personal information reciprocally — regardless of content — creates mutual liking. FBI negotiators use 'tactical disclosure' to build bond quickly: one personal reveal triggers another.",
        "hook_angle": "Why sharing something personal makes someone immediately more likely to trust you"
    },
    {
        "id": "ar_007",
        "category": "attachment",
        "fact": "'Misattribution of arousal' (Dutton & Aron bridge study): People who meet on a high, swaying bridge rate the encounter as more romantic — they attribute the adrenaline of fear to attraction. Exciting situations create false chemistry.",
        "hook_angle": "Why meeting someone in an exciting situation makes you think you're attracted to them"
    },

    # ═════════════════════════════════════════════════════
    # KATEGORIA 8: BEHAWIORALNA EKONOMIA & UMYSŁ KONSUMENTA
    # ═════════════════════════════════════════════════════
    {
        "id": "be_001",
        "category": "behavioral_econ",
        "fact": "Decoy Effect: Adding a third, clearly inferior option to a two-choice set dramatically shifts preference toward the more expensive option — by making the expensive one look like a bargain by comparison.",
        "hook_angle": "The fake third option that's placed there just to make you buy the expensive one"
    },
    {
        "id": "be_002",
        "category": "behavioral_econ",
        "fact": "Price-Quality Heuristic: Studies show people rate identical wines as better-tasting when told they're more expensive — and brain scans confirm actual increased pleasure response, not just a stated preference.",
        "hook_angle": "Why expensive wine literally tastes better than cheap wine — even when it's the same bottle"
    },
    {
        "id": "be_003",
        "category": "behavioral_econ",
        "fact": "Endowment Effect (Kahneman): Owning something immediately increases its perceived value — people demand twice as much to give up something they own versus what they'd pay to acquire the identical item.",
        "hook_angle": "Why things become twice as valuable the moment they belong to you"
    },
    {
        "id": "be_004",
        "category": "behavioral_econ",
        "fact": "Default Effect: When 'opt-out' is set as default (e.g., organ donation, subscription renewal), compliance exceeds 90%. When 'opt-in' is default, compliance drops to below 20%. Default settings are the most powerful choice architecture.",
        "hook_angle": "The invisible default setting that decides more of your choices than you think"
    },
    {
        "id": "be_005",
        "category": "behavioral_econ",
        "fact": "The 'Charm Pricing' effect: Prices ending in .99 activate a sense of bargain even when the rational difference is $0.01. This effect persists even among people who consciously recognize and criticize the tactic.",
        "hook_angle": "Why $9.99 feels meaningfully different from $10 even when you know it's a trick"
    },
    {
        "id": "be_006",
        "category": "behavioral_econ",
        "fact": "Mental Accounting (Thaler): People treat identical sums of money differently based on their source — a $100 tax refund is spent more freely than $100 salary, despite being identical. Where the money comes from changes its psychological 'weight.'",
        "hook_angle": "Why you spend bonus money differently than earned money even though they're the same"
    },
    {
        "id": "be_007",
        "category": "behavioral_econ",
        "fact": "Status Quo Bias: People prefer their current situation and require disproportionate external incentives to change, even when change is objectively beneficial. The brain treats familiar discomfort as safer than unfamiliar improvement.",
        "hook_angle": "Why your brain prefers familiar pain over unfamiliar improvement"
    },
]

# ─── Category order for rotation (ensures variety between videos) ─────────────
CATEGORY_ROTATION = [
    "body_language",
    "cognitive_bias",
    "dark_triad",
    "social_influence",
    "neuropsychology",
    "power_dynamics",
    "attachment",
    "behavioral_econ",
]


class FactSelector:
    """
    Wybiera 3 unikalne fakty z różnych kategorii dla danego wideo.
    Śledzi użyte fakty w accounts/used_facts.json.
    """

    def __init__(self, profile: str = "dark_mindset"):
        self.profile = profile
        self._used = self._load_used()

    def _load_used(self) -> set:
        if not os.path.exists(USED_FACTS_FILE):
            return set()
        try:
            with open(USED_FACTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data.get(self.profile, []))
        except Exception:
            return set()

    def _save_used(self):
        data = {}
        if os.path.exists(USED_FACTS_FILE):
            try:
                with open(USED_FACTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        data[self.profile] = list(self._used)
        os.makedirs(os.path.dirname(USED_FACTS_FILE), exist_ok=True)
        with open(USED_FACTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _get_unused_by_category(self, category: str) -> List[Dict]:
        return [f for f in FACTS_DB if f["category"] == category and f["id"] not in self._used]

    def _reset_category_if_exhausted(self, category: str):
        """Resetuje użyte fakty danej kategorii gdy wszystkie zostały wykorzystane."""
        available = [f for f in FACTS_DB if f["category"] == category]
        used_in_cat = [f for f in available if f["id"] in self._used]
        if len(used_in_cat) >= len(available):
            print(f"  ♻️  [FACTS] Kategoria '{category}' wyczerpana — resetuję pulę tej kategorii.")
            for f in available:
                self._used.discard(f["id"])

    def select_for_video(self, video_index: int, n_facts: int = 3) -> List[Dict]:
        """
        Zwraca n_facts unikalnych faktów z różnych kategorii.
        video_index — pomaga rozstrzygnąć remisy gdy dwa pliki generowane jednocześnie.
        """
        selected = []
        # Przesunięcie indeksu kategorii o video_index — Film 1 i Film 2 mają różne kategorie startowe
        cat_offset = (video_index - 1) * 3
        categories_tried = []

        for i in range(len(CATEGORY_ROTATION)):
            if len(selected) >= n_facts:
                break

            cat = CATEGORY_ROTATION[(cat_offset + i) % len(CATEGORY_ROTATION)]
            if cat in categories_tried:
                continue

            self._reset_category_if_exhausted(cat)
            candidates = self._get_unused_by_category(cat)

            if not candidates:
                continue

            # Wybierz fakt o indeksie opartym na czasie/video_index (deterministyczny ale zróżnicowany)
            import time
            pick_idx = (video_index + int(time.time()) // 60) % len(candidates)
            chosen = candidates[pick_idx]
            selected.append(chosen)
            categories_tried.append(cat)

        # Jeśli wciąż za mało — dobierz z dowolnych kategorii
        if len(selected) < n_facts:
            for fact in FACTS_DB:
                if len(selected) >= n_facts:
                    break
                if fact["id"] not in self._used and fact not in selected:
                    selected.append(fact)

        # Zapisz użyte
        for fact in selected:
            self._used.add(fact["id"])
        self._save_used()

        # Raport
        print(f"\n📚 [FACTS DB] Wybrano {len(selected)} fakty dla wideo #{video_index}:")
        for f in selected:
            print(f"   [{f['category'].upper()}] {f['fact'][:80]}...")

        return selected


def facts_to_prompt_injection(facts: List[Dict]) -> str:
    """Formatuje listę faktów do wstrzyknięcia w prompt AI."""
    lines = ["USE THESE 3 SPECIFIC FACTS as the backbone of your script (build 3 rapid revelations around them):"]
    for i, f in enumerate(facts, 1):
        lines.append(f"\nFACT {i} [{f['category'].upper()}]:")
        lines.append(f"  {f['fact']}")
        lines.append(f"  Hook angle: \"{f['hook_angle']}\"")
    lines.append("\nEach fact = 1-2 sentences MAX in the script. Connect them with escalating impact.")
    lines.append("DO NOT use all 3 as equals — Fact 1 shocks, Fact 2 validates/deepens, Fact 3 gives the viewer a weapon or action.")
    return "\n".join(lines)


if __name__ == "__main__":
    # Test
    selector = FactSelector()
    facts = selector.select_for_video(video_index=1)
    print("\n" + "="*60)
    print(facts_to_prompt_injection(facts))
    print(f"\nŁącznie faktów w bazie: {len(FACTS_DB)}")
    print(f"Kategorii: {len(set(f['category'] for f in FACTS_DB))}")

"""Fixed replies for the three safety outcomes, in English, Hindi and Hinglish.

These are written by hand, not generated. When the message is an emergency, or
the model is down, the patient must get the same correct words every time,
without waiting on (or trusting) another model call.
"""

import re
from enum import Enum


class Language(str, Enum):
    EN = "en"
    HI = "hi"
    HINGLISH = "hinglish"


DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def guess_language(message: str, patient_language: str) -> Language:
    """Used only when the classifier could not tell us. Hindi script is certain;
    otherwise fall back to the language on the patient's record."""
    if DEVANAGARI.search(message):
        return Language.HI
    return Language(patient_language)


_EMERGENCY = {
    Language.EN: (
        "This may be an emergency. Call 112 now. You can also call {hospital} Emergency on {phone}. "
        "I have alerted the care team and a nurse will call you within {minutes} minutes. "
        "Do not wait for the call."
    ),
    Language.HI: (
        "यह आपातकाल हो सकता है। अभी 112 पर कॉल करें। आप {hospital} इमरजेंसी को {phone} पर भी कॉल कर "
        "सकते हैं। मैंने केयर टीम को सूचित कर दिया है और एक नर्स {minutes} मिनट के अंदर आपको कॉल करेगी। "
        "कॉल का इंतज़ार न करें।"
    ),
    Language.HINGLISH: (
        "Yeh emergency ho sakti hai. Abhi 112 par call karein. Aap {hospital} Emergency ko {phone} par "
        "bhi call kar sakte hain. Maine care team ko alert kar diya hai aur ek nurse {minutes} minute "
        "ke andar aapko call karegi. Call ka intezaar na karein."
    ),
}

# If the escalation row itself could not be written, we must not claim the care team was told.
_EMERGENCY_NOT_RECORDED = {
    Language.EN: (
        "This may be an emergency. Call 112 now, or your hospital's emergency desk. "
        "I could not reach the care team from here, so please do not wait for a call back."
    ),
    Language.HI: (
        "यह आपातकाल हो सकता है। अभी 112 पर या अपने अस्पताल के इमरजेंसी डेस्क पर कॉल करें। "
        "मैं यहाँ से केयर टीम तक नहीं पहुँच पाया, इसलिए कृपया कॉल बैक का इंतज़ार न करें।"
    ),
    Language.HINGLISH: (
        "Yeh emergency ho sakti hai. Abhi 112 par ya apne hospital ke emergency desk par call karein. "
        "Main yahan se care team tak nahi pahunch paya, isliye please call back ka intezaar na karein."
    ),
}

_MEDICAL_ADVICE = {
    Language.EN: (
        "I'm not a doctor, so I can't diagnose, suggest medicines or tell you how much to take. "
        "I can book a doctor consultation for you. Would you like me to do that?"
    ),
    Language.HI: (
        "मैं डॉक्टर नहीं हूँ, इसलिए मैं बीमारी नहीं बता सकता, दवा नहीं सुझा सकता और खुराक नहीं बता सकता। "
        "मैं आपके लिए डॉक्टर से परामर्श बुक कर सकता हूँ। क्या मैं बुक कर दूँ?"
    ),
    Language.HINGLISH: (
        "Main doctor nahi hoon, isliye main diagnosis nahi kar sakta, dawai suggest nahi kar sakta aur "
        "dose nahi bata sakta. Main aapke liye doctor consultation book kar sakta hoon. Kya main book kar doon?"
    ),
}

# Fail-closed: the safety check could not run, so the message is not processed at all.
_SAFETY_UNAVAILABLE = {
    Language.EN: (
        "Sorry, I can't process your message right now. If this is an emergency, call 112 immediately "
        "or your hospital's emergency desk. For anything else, please try again in a few minutes, or "
        "call your wellness room to speak to a nurse."
    ),
    Language.HI: (
        "क्षमा करें, मैं अभी आपका संदेश प्रोसेस नहीं कर पा रहा हूँ। अगर यह आपातकाल है तो तुरंत 112 पर या "
        "अपने अस्पताल के इमरजेंसी डेस्क पर कॉल करें। बाकी किसी भी काम के लिए कुछ मिनट बाद फिर कोशिश करें, "
        "या नर्स से बात करने के लिए अपने वेलनेस रूम पर कॉल करें।"
    ),
    Language.HINGLISH: (
        "Sorry, main abhi aapka message process nahi kar pa raha hoon. Agar yeh emergency hai to turant "
        "112 par ya apne hospital ke emergency desk par call karein. Baaki kisi bhi kaam ke liye kuch "
        "minute baad dobara try karein, ya nurse se baat karne ke liye apne wellness room par call karein."
    ),
}


def emergency(language: Language, *, hospital: str, phone: str, minutes: int) -> str:
    return _EMERGENCY[language].format(hospital=hospital, phone=phone, minutes=minutes)


def emergency_not_recorded(language: Language) -> str:
    return _EMERGENCY_NOT_RECORDED[language]


def medical_advice(language: Language) -> str:
    return _MEDICAL_ADVICE[language]


def safety_unavailable(language: Language) -> str:
    return _SAFETY_UNAVAILABLE[language]

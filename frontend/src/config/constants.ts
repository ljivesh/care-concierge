// App-wide constants: the brand, the seed patients and the starter prompts.

import { CalendarPlus, ClipboardList, HeartPulse, Stethoscope, type LucideIcon } from "lucide-react";
import type { Language, Patient } from "@/lib/types/concierge";

export const APP_NAME = "Care Concierge";
export const ORG_NAME = "MicroHeal";
export const BrandIcon = HeartPulse;

const patient = (id: string, name: string, society: string, language: Language): Patient => ({
  id,
  name,
  society,
  language,
});

/** The 20 seed patients. A real app would know the patient from their login. */
export const PATIENTS: Patient[] = [
  patient("pat_001", "Ananya Sharma", "Shivalik Greens", "hinglish"),
  patient("pat_002", "Rajesh Gupta", "Shivalik Greens", "hi"),
  patient("pat_003", "Priya Nair", "Shivalik Greens", "en"),
  patient("pat_004", "Vikram Malhotra", "Shivalik Greens", "hinglish"),
  patient("pat_005", "Kamla Devi", "Shivalik Greens", "hi"),
  patient("pat_006", "Arjun Mehta", "Shivalik Greens", "en"),
  patient("pat_007", "Sneha Kulkarni", "Shivalik Greens", "en"),
  patient("pat_008", "Mohammed Faisal", "Shivalik Greens", "hinglish"),
  patient("pat_009", "Deepa Iyer", "Lotus Tower", "en"),
  patient("pat_010", "Suresh Yadav", "Lotus Tower", "hi"),
  patient("pat_011", "Pooja Agarwal", "Lotus Tower", "hinglish"),
  patient("pat_012", "Harpreet Singh", "Lotus Tower", "hinglish"),
  patient("pat_013", "Lakshmi Krishnan", "Lotus Tower", "en"),
  patient("pat_014", "Amit Verma", "Lotus Tower", "hi"),
  patient("pat_015", "Neelam Chauhan", "Lotus Tower", "hinglish"),
  patient("pat_016", "Sanjay Bhatia", "Royal Palms", "en"),
  patient("pat_017", "Ritu Saxena", "Royal Palms", "hinglish"),
  patient("pat_018", "Ramesh Tiwari", "Royal Palms", "hi"),
  patient("pat_019", "Fatima Sheikh", "Royal Palms", "en"),
  patient("pat_020", "Gaurav Chopra", "Royal Palms", "hinglish"),
];

export const DEFAULT_PATIENT_ID = PATIENTS[0].id;

export const SOCIETIES = [...new Set(PATIENTS.map((p) => p.society))];

export const LANGUAGE_LABEL: Record<Language, string> = {
  en: "English",
  hi: "हिंदी",
  hinglish: "Hinglish",
};

export interface StarterPrompt {
  icon: LucideIcon;
  title: string;
  /** The message that is sent, in each language a patient may write in. */
  prompt: Record<Language, string>;
}

/** The four things the concierge does, offered on an empty conversation. */
export const STARTER_PROMPTS: StarterPrompt[] = [
  {
    icon: CalendarPlus,
    title: "Book an appointment",
    prompt: {
      en: "I'd like to book a general physician appointment",
      hi: "मुझे सामान्य चिकित्सक का अपॉइंटमेंट बुक करना है",
      hinglish: "Mujhe general physician ka appointment book karna hai",
    },
  },
  {
    icon: ClipboardList,
    title: "See my bookings",
    prompt: {
      en: "Show my bookings",
      hi: "मेरी बुकिंग दिखाइए",
      hinglish: "Meri bookings dikhao",
    },
  },
  {
    icon: Stethoscope,
    title: "Note a symptom",
    prompt: {
      en: "I've had a mild headache for two days, severity 2. Please note it.",
      hi: "मुझे दो दिन से हल्का सिर दर्द है, गंभीरता 2। कृपया नोट कर लीजिए।",
      hinglish: "2 din se halka sar dard hai, severity 2. Note kar lo.",
    },
  },
  {
    icon: HeartPulse,
    title: "Ask about the clinic",
    prompt: {
      en: "What time does the wellness room open on Sunday?",
      hi: "रविवार को वेलनेस रूम कितने बजे खुलता है?",
      hinglish: "Sunday ko wellness room kab khulta hai?",
    },
  },
];

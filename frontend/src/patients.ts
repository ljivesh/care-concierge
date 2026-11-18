// The 20 seed patients. A real app would know the patient from their login.

export interface Patient {
  id: string;
  name: string;
  society: string;
}

const row = (id: string, name: string, society: string): Patient => ({ id, name, society });

export const PATIENTS: Patient[] = [
  row("pat_001", "Ananya Sharma", "Shivalik Greens"),
  row("pat_002", "Rajesh Gupta", "Shivalik Greens"),
  row("pat_003", "Priya Nair", "Shivalik Greens"),
  row("pat_004", "Vikram Malhotra", "Shivalik Greens"),
  row("pat_005", "Kamla Devi", "Shivalik Greens"),
  row("pat_006", "Arjun Mehta", "Shivalik Greens"),
  row("pat_007", "Sneha Kulkarni", "Shivalik Greens"),
  row("pat_008", "Mohammed Faisal", "Shivalik Greens"),
  row("pat_009", "Deepa Iyer", "Lotus Tower"),
  row("pat_010", "Suresh Yadav", "Lotus Tower"),
  row("pat_011", "Pooja Agarwal", "Lotus Tower"),
  row("pat_012", "Harpreet Singh", "Lotus Tower"),
  row("pat_013", "Lakshmi Krishnan", "Lotus Tower"),
  row("pat_014", "Amit Verma", "Lotus Tower"),
  row("pat_015", "Neelam Chauhan", "Lotus Tower"),
  row("pat_016", "Sanjay Bhatia", "Royal Palms"),
  row("pat_017", "Ritu Saxena", "Royal Palms"),
  row("pat_018", "Ramesh Tiwari", "Royal Palms"),
  row("pat_019", "Fatima Sheikh", "Royal Palms"),
  row("pat_020", "Gaurav Chopra", "Royal Palms"),
];

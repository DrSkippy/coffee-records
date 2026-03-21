export type RoastLevel = "light" | "medium" | "dark";
export type GrinderType = "flat" | "conical" | "blade";
export type DrinkType = "americano" | "latte" | "cappuccino" | "drip";
export type Maker = "Scott" | "Sara";

export interface Coffee {
  id: number;
  name: string;
  roaster: string;
  roast_date: string | null;
  origin_country: string | null;
  roast_level: RoastLevel | null;
  variety: string | null;
  process: string | null;
  created_at: string;
}

export interface Grinder {
  id: number;
  make: string;
  model: string;
  type: GrinderType;
  notes: string | null;
  created_at: string;
}

export interface BrewingDevice {
  id: number;
  make: string;
  model: string;
  type: string;
  warmup_minutes: number | null;
  notes: string | null;
  created_at: string;
}

export interface Scale {
  id: number;
  make: string;
  model: string;
  notes: string | null;
  created_at: string;
}

export interface Shot {
  id: number;
  date: string;
  maker: Maker;
  coffee_id: number | null;
  coffee_name: string | null;
  dose_weight: number | null;
  pre_infusion_time: string | null;
  extraction_time: number | null;
  scale_id: number | null;
  scale_label: string | null;
  final_weight: number | null;
  drink_type: DrinkType | null;
  grinder_temp_before: number | null;
  grinder_temp_after: number | null;
  wedge: boolean;
  shaker: boolean;
  wdt: boolean;
  flow_taper: boolean;
  notes: string | null;
  grinder_id: number | null;
  grinder_label: string | null;
  device_id: number | null;
  device_label: string | null;
  created_at: string;
}

export interface DoseYieldPoint {
  date: string;
  shot_id: number;
  dose_weight: number;
  final_weight: number;
  ratio: number | null;
}

export interface ShotsPerDayPoint {
  date: string;
  count: number;
}

export interface ExtractionPoint {
  date: string;
  shot_id: number;
  extraction_time: number;
}

export interface ByCoffeeReport {
  coffee_id: number;
  total_shots: number;
  avg_dose: number | null;
  avg_final_weight: number | null;
  avg_extraction_time: number | null;
  avg_ratio: number | null;
  shots: Array<{
    date: string;
    shot_id: number;
    dose_weight: number | null;
    final_weight: number | null;
    extraction_time: number | null;
  }>;
}

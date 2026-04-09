export type RoastLevel = "light" | "medium" | "dark";
export type GrinderType = "flat" | "conical" | "blade";
export type DrinkType = "americano" | "latte" | "cappuccino" | "drip" | "aeropress";
export type Maker = string;

export interface Coffee {
  id: number;
  name: string;
  roaster: string;
  roast_date: string | null;
  origin_country: string | null;
  roast_level: RoastLevel | null;
  variety: string | null;
  process: string | null;
  image_filename: string | null;
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
  extraction_delta: number | null;
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
  grind_setting: string | null;
  notes: string | null;
  video_filename: string | null;
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
  device_id: number | null;
  device_label: string | null;
}

export interface ShotsPerDayPoint {
  date: string;
  count: number;
}

export interface ExtractionPoint {
  date: string;
  shot_id: number;
  extraction_time: number;
  device_id: number | null;
  device_label: string | null;
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

export interface GrindRegressionPoint {
  shot_id: number;
  date: string;
  x1: number;
  x2: number;
  y: number;
  y_str: string;
  y_predicted: number;
  y_predicted_str: string;
}

export interface GrindRegressionGrinder {
  grinder_id: number;
  grinder_label: string;
  n_shots: number;
  coefficients: { a: number; b: number; c: number };
  r_squared: number | null;
  points: GrindRegressionPoint[];
}

export interface GrindRegressionResult {
  coffee_id: number;
  roast_date: string;
  grinders: GrindRegressionGrinder[];
  target_shot_time: number | null;
}

export interface CoffeeInterceptItem {
  coffee_id: number;
  coffee_name: string | null;
  intercept: number;
}

export interface TargetTimeItem {
  coffee_id: number;
  target_shot_time: number | null;
}

export interface GrindModelPoint {
  shot_id: number;
  date: string;
  age_days: number;
  temp_offset: number;
  grind: number;
  grind_str: string;
  grind_predicted: number;
  grind_predicted_str: string;
}

export interface GrindModelTraining {
  training_id: number;
  grinder_id: number;
  grinder_label: string;
  trained_at: string;
  n_shots_available: number;
  n_shots_used: number;
  n_coffees: number;
  n_iterations: number;
  converged: boolean;
  r_squared: number | null;
  a0: number;
  a2: number;
  a3: number;
  a4: number;
  a5: number;
  coffee_intercepts: CoffeeInterceptItem[];
}

export interface GrindModelParamsResult extends GrindModelTraining {
  points: GrindModelPoint[];
  target_times: TargetTimeItem[];
}

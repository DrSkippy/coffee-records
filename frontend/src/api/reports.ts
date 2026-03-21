import type {
  ByCoffeeReport,
  DoseYieldPoint,
  ExtractionPoint,
  ShotsPerDayPoint,
} from "../types";
import api from "./client";

interface DateRange {
  date_from?: string;
  date_to?: string;
}

export const getDoseYield = (params: DateRange = {}) =>
  api.get<DoseYieldPoint[]>("/reports/dose-yield", { params }).then((r) => r.data);

export const getShotsPerDay = (params: DateRange = {}) =>
  api.get<ShotsPerDayPoint[]>("/reports/shots-per-day", { params }).then((r) => r.data);

export const getExtractionTrends = (params: DateRange = {}) =>
  api.get<ExtractionPoint[]>("/reports/extraction-trends", { params }).then((r) => r.data);

export const getByCoffee = (coffeeId: number, params: DateRange = {}) =>
  api
    .get<ByCoffeeReport>(`/reports/by-coffee/${coffeeId}`, { params })
    .then((r) => r.data);

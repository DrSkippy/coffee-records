import type {
  ByCoffeeReport,
  DoseYieldPoint,
  ExtractionPoint,
  GrindRegressionResult,
  ShotsPerDayPoint,
} from "../types";
import api from "./client";

interface ReportParams {
  date_from?: string;
  date_to?: string;
  coffee_id?: number;
  grinder_id?: number;
  device_id?: number;
}

export const getDoseYield = (params: ReportParams = {}) =>
  api.get<DoseYieldPoint[]>("/reports/dose-yield", { params }).then((r) => r.data);

export const getShotsPerDay = (params: ReportParams = {}) =>
  api.get<ShotsPerDayPoint[]>("/reports/shots-per-day", { params }).then((r) => r.data);

export const getExtractionTrends = (params: ReportParams = {}) =>
  api.get<ExtractionPoint[]>("/reports/extraction-trends", { params }).then((r) => r.data);

export const getByCoffee = (coffeeId: number, params: ReportParams = {}) =>
  api
    .get<ByCoffeeReport>(`/reports/by-coffee/${coffeeId}`, { params })
    .then((r) => r.data);

export const getGrindRegression = (coffeeId: number, grinderId?: number) =>
  api
    .get<GrindRegressionResult>("/reports/grind-regression", {
      params: { coffee_id: coffeeId, ...(grinderId ? { grinder_id: grinderId } : {}) },
    })
    .then((r) => r.data);

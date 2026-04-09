import type {
  ByCoffeeReport,
  DoseYieldPoint,
  ExtractionPoint,
  GrindModelParamsResult,
  GrindModelTraining,
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

export const trainGrindModel = (grinderId: number) =>
  api
    .post<GrindModelTraining>(`/reports/grind-model/train?grinder_id=${grinderId}`)
    .then((r) => r.data);

export const getGrindModelParams = (
  grinderId: number,
  opts: { trainingId?: number; asOf?: string } = {}
) =>
  api
    .get<GrindModelParamsResult>("/reports/grind-model/params", {
      params: {
        grinder_id: grinderId,
        ...(opts.trainingId ? { training_id: opts.trainingId } : {}),
        ...(opts.asOf ? { as_of: opts.asOf } : {}),
      },
    })
    .then((r) => r.data);

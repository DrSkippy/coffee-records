import type { Shot } from "../types";
import api from "./client";

interface ShotFilters {
  maker?: string;
  coffee_id?: number;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export const getShots = (filters: ShotFilters = {}) =>
  api.get<Shot[]>("/shots", { params: filters }).then((r) => r.data);

export const getShot = (id: number) =>
  api.get<Shot>(`/shots/${id}`).then((r) => r.data);

export const createShot = (data: Partial<Shot>) =>
  api.post<Shot>("/shots", data).then((r) => r.data);

export const updateShot = (id: number, data: Partial<Shot>) =>
  api.put<Shot>(`/shots/${id}`, data).then((r) => r.data);

export const deleteShot = (id: number) => api.delete(`/shots/${id}`);

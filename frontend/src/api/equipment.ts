import type { BrewingDevice, Grinder, Scale } from "../types";
import api from "./client";

export const getGrinders = () => api.get<Grinder[]>("/grinders").then((r) => r.data);
export const createGrinder = (data: Partial<Grinder>) =>
  api.post<Grinder>("/grinders", data).then((r) => r.data);
export const updateGrinder = (id: number, data: Partial<Grinder>) =>
  api.put<Grinder>(`/grinders/${id}`, data).then((r) => r.data);
export const deleteGrinder = (id: number) => api.delete(`/grinders/${id}`);

export const getBrewingDevices = () =>
  api.get<BrewingDevice[]>("/brewing-devices").then((r) => r.data);
export const createBrewingDevice = (data: Partial<BrewingDevice>) =>
  api.post<BrewingDevice>("/brewing-devices", data).then((r) => r.data);
export const updateBrewingDevice = (id: number, data: Partial<BrewingDevice>) =>
  api.put<BrewingDevice>(`/brewing-devices/${id}`, data).then((r) => r.data);
export const deleteBrewingDevice = (id: number) => api.delete(`/brewing-devices/${id}`);

export const getScales = () => api.get<Scale[]>("/scales").then((r) => r.data);
export const createScale = (data: Partial<Scale>) =>
  api.post<Scale>("/scales", data).then((r) => r.data);
export const updateScale = (id: number, data: Partial<Scale>) =>
  api.put<Scale>(`/scales/${id}`, data).then((r) => r.data);
export const deleteScale = (id: number) => api.delete(`/scales/${id}`);

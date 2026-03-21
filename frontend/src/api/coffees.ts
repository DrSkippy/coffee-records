import type { Coffee } from "../types";
import api from "./client";

export const getCoffees = () => api.get<Coffee[]>("/coffees").then((r) => r.data);

export const getCoffee = (id: number) =>
  api.get<Coffee>(`/coffees/${id}`).then((r) => r.data);

export const createCoffee = (data: Partial<Coffee>) =>
  api.post<Coffee>("/coffees", data).then((r) => r.data);

export const updateCoffee = (id: number, data: Partial<Coffee>) =>
  api.put<Coffee>(`/coffees/${id}`, data).then((r) => r.data);

export const deleteCoffee = (id: number) => api.delete(`/coffees/${id}`);

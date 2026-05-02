import type { ShotDefaults } from "../types";
import api from "./client";

export const getDefaults = () =>
  api.get<ShotDefaults>("/defaults").then((r) => r.data);

export const updateDefaults = (data: Omit<ShotDefaults, "id" | "updated_at">) =>
  api.put<ShotDefaults>("/defaults", data).then((r) => r.data);

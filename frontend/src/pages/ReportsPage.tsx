import { BarChart, LineChart } from "@mantine/charts";
import { Badge, Group, Paper, Select, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { useEffect, useState } from "react";
import {
  getDoseYield,
  getExtractionTrends,
  getShotsPerDay,
  getShotsPerGrinder,
} from "../api/reports";
import { getCoffees } from "../api/coffees";
import { getBrewingDevices } from "../api/equipment";
import type {
  BrewingDevice,
  Coffee,
  DoseYieldPoint,
  ExtractionPoint,
  GrinderShotCount,
  ShotsPerDayPoint,
} from "../types";

const DEVICE_COLORS = [
  "coffee.6",
  "coffee.4",
  "coffee.8",
  "coffee.2",
  "coffee.9",
];

function deviceColor(index: number): string {
  return DEVICE_COLORS[index % DEVICE_COLORS.length];
}

/** Unique device labels from a dataset, preserving first-seen order. */
function uniqueDevices(points: { device_label: string | null }[]): string[] {
  const seen = new Set<string>();
  const labels: string[] = [];
  for (const p of points) {
    const label = p.device_label ?? "Unknown";
    if (!seen.has(label)) {
      seen.add(label);
      labels.push(label);
    }
  }
  return labels;
}

/**
 * Pivot flat per-shot data into the multi-series format Mantine LineChart expects.
 * Each row gets its device's value set, all other device keys are null.
 */
function pivotByDevice<T extends { date: string; device_label: string | null }>(
  points: T[],
  valueKey: keyof T,
  devices: string[]
): Record<string, unknown>[] {
  return points.map((p) => {
    const label = p.device_label ?? "Unknown";
    const row: Record<string, unknown> = { date: p.date };
    for (const d of devices) {
      row[d] = d === label ? p[valueKey] : null;
    }
    return row;
  });
}

const DATE_RANGES = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
];

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

interface ReportParams {
  date_from: string;
  date_to: string;
  coffee_id?: number;
  device_id?: number;
}

interface GrinderPanelProps {
  grinder: GrinderShotCount;
  params: ReportParams;
}

function GrinderPanel({ grinder, params }: GrinderPanelProps) {
  const [doseYield, setDoseYield] = useState<DoseYieldPoint[]>([]);
  const [perDay, setPerDay] = useState<ShotsPerDayPoint[]>([]);
  const [extraction, setExtraction] = useState<ExtractionPoint[]>([]);

  useEffect(() => {
    const p = { ...params, grinder_id: grinder.grinder_id };
    getDoseYield(p).then(setDoseYield);
    getShotsPerDay(p).then(setPerDay);
    getExtractionTrends(p).then(setExtraction);
  }, [grinder.grinder_id, params]);

  const extractionDevices = uniqueDevices(extraction);
  const extractionSeries = extractionDevices.map((d, i) => ({
    name: d,
    color: deviceColor(i),
    label: d,
  }));
  const extractionData = pivotByDevice(extraction, "extraction_time", extractionDevices);

  const doseYieldDevices = uniqueDevices(doseYield);
  const ratioSeries = doseYieldDevices.map((d, i) => ({
    name: d,
    color: deviceColor(i),
    label: d,
  }));
  const ratioData = pivotByDevice(doseYield, "ratio", doseYieldDevices);

  const doseVsYieldSeries = doseYieldDevices.flatMap((d, i) => [
    { name: `${d} dose`, color: deviceColor(i), label: `${d} — Dose` },
    { name: `${d} yield`, color: deviceColor(i), label: `${d} — Yield` },
  ]);
  const doseVsYieldData = doseYield.map((p) => {
    const label = p.device_label ?? "Unknown";
    const row: Record<string, unknown> = { date: p.date };
    for (const d of doseYieldDevices) {
      row[`${d} dose`] = d === label ? p.dose_weight : null;
      row[`${d} yield`] = d === label ? p.final_weight : null;
    }
    return row;
  });

  return (
    <Paper withBorder p="md">
      <Group mb="md" align="center">
        <Title order={3}>{grinder.make} {grinder.model}</Title>
        <Badge variant="light" color="coffee">{grinder.count} shots</Badge>
      </Group>
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
        <Stack>
          <Title order={4}>Shots per Day</Title>
          {perDay.length === 0 ? (
            <Text c="dimmed">No data</Text>
          ) : (
            <BarChart
              h={200}
              data={perDay}
              dataKey="date"
              series={[{ name: "count", color: "coffee.9", label: "Shots" }]}
            />
          )}
        </Stack>

        <Stack>
          <Title order={4}>Extraction Time (s)</Title>
          {extraction.length === 0 ? (
            <Text c="dimmed">No data</Text>
          ) : (
            <LineChart
              h={200}
              data={extractionData}
              dataKey="date"
              series={extractionSeries}
              curveType="monotone"
            />
          )}
        </Stack>

        <Stack>
          <Title order={4}>Dose:Yield Ratio</Title>
          {doseYield.length === 0 ? (
            <Text c="dimmed">No data</Text>
          ) : (
            <LineChart
              h={200}
              data={ratioData}
              dataKey="date"
              series={ratioSeries}
              curveType="monotone"
            />
          )}
        </Stack>

        <Stack>
          <Title order={4}>Dose vs Yield (g)</Title>
          {doseYield.length === 0 ? (
            <Text c="dimmed">No data</Text>
          ) : (
            <LineChart
              h={200}
              data={doseVsYieldData}
              dataKey="date"
              series={doseVsYieldSeries}
              curveType="monotone"
            />
          )}
        </Stack>
      </SimpleGrid>
    </Paper>
  );
}

export default function ReportsPage() {
  const [days, setDays] = useState("30");
  const [coffeeId, setCoffeeId] = useState<string | null>(null);
  const [deviceId, setDeviceId] = useState<string | null>(null);

  const [coffees, setCoffees] = useState<Coffee[]>([]);
  const [devices, setDevices] = useState<BrewingDevice[]>([]);
  const [grinderCounts, setGrinderCounts] = useState<GrinderShotCount[]>([]);

  // Load filter options once
  useEffect(() => {
    getCoffees().then(setCoffees);
    getBrewingDevices().then(setDevices);
  }, []);

  const params: ReportParams = {
    date_from: daysAgo(Number(days)),
    date_to: new Date().toISOString().slice(0, 10),
    ...(coffeeId ? { coffee_id: Number(coffeeId) } : {}),
    ...(deviceId ? { device_id: Number(deviceId) } : {}),
  };

  // Reload grinder counts whenever filters change
  useEffect(() => {
    getShotsPerGrinder(params).then(setGrinderCounts);
  }, [days, coffeeId, deviceId]);

  const activeGrinders = grinderCounts.filter((g) => g.count > 3);

  const coffeeOptions = coffees.map((c) => ({
    value: String(c.id),
    label: `${c.roaster} — ${c.name}`,
  }));
  const deviceOptions = devices.map((d) => ({
    value: String(d.id),
    label: `${d.make} ${d.model}`,
  }));

  return (
    <Stack>
      <Title order={2}>Reports</Title>

      <Group align="flex-end" wrap="wrap">
        <Select
          label="Date range"
          data={DATE_RANGES}
          value={days}
          onChange={(v) => setDays(v ?? "30")}
          w={160}
        />
        <Select
          label="Coffee"
          data={coffeeOptions}
          value={coffeeId}
          onChange={setCoffeeId}
          placeholder="All coffees"
          clearable
          w={220}
        />
        <Select
          label="Equipment"
          data={deviceOptions}
          value={deviceId}
          onChange={setDeviceId}
          placeholder="All devices"
          clearable
          w={200}
        />
      </Group>

      {activeGrinders.length === 0 ? (
        <Text c="dimmed">No grinders with more than 3 shots in this period.</Text>
      ) : (
        <Stack gap="lg">
          {activeGrinders.map((g) => (
            <GrinderPanel key={g.grinder_id} grinder={g} params={params} />
          ))}
        </Stack>
      )}
    </Stack>
  );
}

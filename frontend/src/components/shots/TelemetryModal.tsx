import { LineChart } from "@mantine/charts";
import { Center, Loader, Modal, Text } from "@mantine/core";
import { useEffect, useState } from "react";
import type { Shot } from "../../types";

const TELEMETRY_BASE_URL = "https://resources.drskippy.app/coffee/telemetry";

interface SeriesPoint {
  brew_time: number;
  [key: string]: number | undefined;
}

interface SeriesDef {
  name: string;
  color: string;
  key: string;
  yAxisId: "left" | "right";
}

const SERIES_CONFIG: SeriesDef[] = [
  { name: "Weight (g)", color: "blue.6", key: "weight", yAxisId: "right" },
  { name: "Flow (g/s)", color: "teal.6", key: "flow", yAxisId: "left" },
  { name: "Pressure (bar)", color: "orange.6", key: "pressure", yAxisId: "left" },
];

function parseBrewTime(s: string): number {
  // Beanconqueror uses S.T format where T is tenths of a second, not a
  // decimal fraction. '0.10' means 1.0 s, not 0.1 s.
  const dot = s.indexOf(".");
  if (dot === -1) return parseFloat(s);
  return parseInt(s.slice(0, dot), 10) + parseInt(s.slice(dot + 1), 10) / 10;
}

function extractSeries(
  raw: Record<string, unknown[]>
): { data: SeriesPoint[]; activeSeries: SeriesDef[] } {
  type RawEntry = Record<string, unknown>;

  const extractors: Record<string, (entry: RawEntry) => number | undefined> = {
    weight: (e) => (e.actual_smoothed_weight as number) ?? undefined,
    flow: (e) => (e.flow_value as number) ?? undefined,
    pressure: (e) => (e.actual_pressure as number) ?? undefined,
  };

  const sourceArrays: Record<string, unknown[]> = {
    weight: raw.weight ?? [],
    flow: raw.realtimeFlow ?? [],
    pressure: raw.pressureFlow ?? [],
  };

  const seriesMaps: Record<string, Map<number, number>> = {};
  const allTimes = new Set<number>();

  for (const cfg of SERIES_CONFIG) {
    const arr = sourceArrays[cfg.key] as RawEntry[];
    const map = new Map<number, number>();
    for (const entry of arr) {
      const t = parseBrewTime(entry.brew_time as string);
      const v = extractors[cfg.key](entry);
      if (!isNaN(t) && v !== undefined) {
        map.set(t, v);
        allTimes.add(t);
      }
    }
    seriesMaps[cfg.key] = map;
  }

  const activeSeries = SERIES_CONFIG.filter((cfg) => {
    const map = seriesMaps[cfg.key];
    return [...map.values()].some((v) => v !== 0);
  });

  const sortedTimes = [...allTimes].sort((a, b) => a - b);
  const data: SeriesPoint[] = sortedTimes.map((t) => {
    const point: SeriesPoint = { brew_time: t };
    for (const cfg of activeSeries) {
      const v = seriesMaps[cfg.key].get(t);
      if (v !== undefined) point[cfg.key] = v;
    }
    return point;
  });

  return { data, activeSeries };
}

export default function TelemetryModal({
  shot,
  opened,
  onClose,
}: {
  shot: Shot;
  opened: boolean;
  onClose: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chartData, setChartData] = useState<SeriesPoint[]>([]);
  const [activeSeries, setActiveSeries] = useState<SeriesDef[]>([]);

  useEffect(() => {
    if (!opened || !shot.telemetry_filename) return;
    setLoading(true);
    setError(null);
    fetch(`${TELEMETRY_BASE_URL}/${shot.telemetry_filename}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((raw) => {
        const { data, activeSeries: active } = extractSeries(raw);
        setChartData(data);
        setActiveSeries(active);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [opened, shot.telemetry_filename]);

  const hasRightAxis = activeSeries.some((s) => s.yAxisId === "right");

  const computeMax = (keys: string[]) => {
    if (keys.length === 0 || chartData.length === 0) return 10;
    const max = chartData.reduce(
      (m, d) => Math.max(m, ...keys.map((k) => (d[k] as number) ?? 0)),
      0
    );
    return Math.ceil(max * 1.1);
  };

  const leftKeys = activeSeries.filter((s) => s.yAxisId === "left").map((s) => s.key);
  const rightKeys = activeSeries.filter((s) => s.yAxisId === "right").map((s) => s.key);
  const leftMax = computeMax(leftKeys);
  const rightMax = computeMax(rightKeys);
  const leftDomain: [number, number] = [0, leftMax];
  const rightDomain: [number, number] = [0, rightMax];
  const leftTicks = Array.from({ length: Math.floor(leftMax / 2) + 1 }, (_, i) => i * 2);

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={`Shot Telemetry — ${shot.date}`}
      size="xl"
    >
      {loading && (
        <Center h={300}>
          <Loader />
        </Center>
      )}
      {error && (
        <Center h={300}>
          <Text c="red">Failed to load telemetry: {error}</Text>
        </Center>
      )}
      {!loading && !error && chartData.length > 0 && (
        <LineChart
          h={420}
          data={chartData}
          dataKey="brew_time"
          series={activeSeries.map((s) => ({
            name: s.key,
            label: s.name,
            color: s.color,
            yAxisId: s.yAxisId,
          }))}
          curveType="linear"
          withLegend
          withDots={false}
          xAxisLabel="Time (s)"
          withRightYAxis={hasRightAxis}
          yAxisLabel="Flow / Pressure / Temp"
          rightYAxisLabel="Weight (g)"
          yAxisProps={{ domain: leftDomain, ticks: leftTicks, tickFormatter: (v: number) => String(v) }}
          rightYAxisProps={{ domain: rightDomain }}
        />
      )}
      {!loading && !error && chartData.length === 0 && (
        <Center h={300}>
          <Text c="dimmed">No data</Text>
        </Center>
      )}
    </Modal>
  );
}

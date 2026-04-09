import {
  Button,
  Card,
  Group,
  Loader,
  NumberInput,
  Select,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useEffect, useState } from "react";
import { getCoffees } from "../api/coffees";
import { getGrinders } from "../api/equipment";
import { getGrindModelParams, trainGrindModel } from "../api/reports";
import type { Coffee, Grinder, GrindModelParamsResult } from "../types";

interface HistBin {
  label: string;
  range: string;
  count: number;
  hasSelected: boolean;
  coffees: string[];
}

function formatGrind(v: number): string {
  const FRAC_MAP: Record<number, string> = { 0.25: "1/4", 0.5: "1/2", 0.75: "3/4" };
  if (v < 30) return String(Math.round(v * 100) / 100);
  const g = Math.floor(v / 10);
  const rem = v - g * 10;
  let h = Math.floor(rem);
  let frac = Math.round((rem - h) * 4) / 4;
  if (frac >= 1) {
    h += 1;
    frac = 0;
  }
  if (frac === 0) return `${g}+${h}`;
  return `${g}+${h} ${FRAC_MAP[frac] ?? String(frac)}`;
}

function daysSince(isoDate: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const roast = new Date(isoDate);
  roast.setHours(0, 0, 0, 0);
  return Math.round((today.getTime() - roast.getTime()) / 86_400_000);
}

function fmtTerm(coeff: number, varName: string): string {
  const sign = coeff >= 0 ? "+" : "−";
  return `${sign} ${Math.abs(coeff).toFixed(4)} · ${varName}`;
}

function buildHistBins(
  intercepts: GrindModelParamsResult["coffee_intercepts"],
  selectedIntercept: number | null
): HistBin[] {
  if (intercepts.length === 0) return [];
  const vals = intercepts.map((ci) => ci.intercept);
  const BIN_W = 0.5;
  const minV = Math.floor(Math.min(...vals) / BIN_W) * BIN_W;
  const maxV = Math.ceil(Math.max(...vals) / BIN_W) * BIN_W;
  const nBins = Math.round((maxV - minV) / BIN_W) + 1;
  return Array.from({ length: nBins }, (_, i) => {
    const lo = minV + i * BIN_W;
    const hi = lo + BIN_W;
    const inBin = intercepts.filter((ci) => ci.intercept >= lo && ci.intercept < hi);
    return {
      label: formatGrind(lo),
      range: `${formatGrind(lo)} – ${formatGrind(hi)}`,
      count: inBin.length,
      hasSelected:
        selectedIntercept !== null &&
        selectedIntercept >= lo &&
        selectedIntercept < hi,
      coffees: inBin.map((ci) => ci.coffee_name ?? `#${ci.coffee_id}`),
    };
  }).filter((b) => b.count > 0);
}

function HistTooltipContent({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: HistBin }>;
}) {
  if (!active || !payload?.length) return null;
  const bin = payload[0].payload;
  return (
    <Card shadow="sm" padding="xs" withBorder style={{ maxWidth: 220 }}>
      <Text size="xs" fw={600}>
        {bin.range}
      </Text>
      {bin.coffees.map((name, i) => (
        <Text key={i} size="xs">
          {name}
        </Text>
      ))}
    </Card>
  );
}

export default function ShotPlannerPage() {
  const [coffees, setCoffees] = useState<Coffee[]>([]);
  const [grinders, setGrinders] = useState<Grinder[]>([]);
  const [coffeeId, setCoffeeId] = useState<string | null>(null);
  const [grinderId, setGrinderId] = useState<string | null>(null);
  const [params, setParams] = useState<GrindModelParamsResult | null>(null);
  const [modelError, setModelError] = useState<string | null>(null);
  const [loadingModel, setLoadingModel] = useState(false);
  const [temp, setTemp] = useState<number | string>(64);
  const [retraining, setRetraining] = useState(false);
  const [retrainError, setRetrainError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getCoffees(), getGrinders()]).then(([c, g]) => {
      setCoffees(c);
      setGrinders(g);
    });
  }, []);

  useEffect(() => {
    if (!grinderId) {
      setParams(null);
      setModelError(null);
      return;
    }
    setLoadingModel(true);
    setParams(null);
    setModelError(null);
    getGrindModelParams(Number(grinderId))
      .then((r) => {
        setParams(r);
      })
      .catch((err) => {
        const status = err?.response?.status;
        if (status === 404) {
          setModelError(
            "No trained model found for this grinder. Use the Retrain Model button to train one."
          );
        } else {
          setModelError("Failed to load model parameters.");
        }
      })
      .finally(() => setLoadingModel(false));
  }, [grinderId]);

  const handleRetrain = () => {
    if (!grinderId) return;
    setRetraining(true);
    setRetrainError(null);
    trainGrindModel(Number(grinderId))
      .then(() => getGrindModelParams(Number(grinderId)))
      .then((r) => {
        setParams(r);
        setModelError(null);
      })
      .catch((err) => {
        const status = err?.response?.status;
        if (status === 422) {
          setRetrainError("Insufficient data — fewer than 3 usable shots after filtering.");
        } else {
          setRetrainError("Retraining failed.");
        }
      })
      .finally(() => setRetraining(false));
  };

  const coffeeData = coffees.map((c) => ({
    value: String(c.id),
    label: `${c.name} — ${c.roaster}${c.roast_date ? ` (${c.roast_date})` : ""}`,
  }));

  const grinderData = grinders.map((g) => ({
    value: String(g.id),
    label: `${g.make} ${g.model}`,
  }));

  const selectedCoffee = coffees.find((c) => c.id === Number(coffeeId)) ?? null;
  const ageDays = selectedCoffee?.roast_date ? daysSince(selectedCoffee.roast_date) : null;
  const coffeeIntercept =
    params?.coffee_intercepts.find((ci) => ci.coffee_id === Number(coffeeId))?.intercept ?? null;
  const targetTime =
    params?.target_times.find((t) => t.coffee_id === Number(coffeeId))?.target_shot_time ?? null;
  const tempNum = typeof temp === "number" ? temp : null;
  const predicted =
    params && coffeeIntercept !== null && ageDays !== null && tempNum !== null
      ? params.a0 * (tempNum - 65) + params.a4 * ageDays + coffeeIntercept
      : null;

  // Plot 1 — grind vs days since roast
  const x1Values = params?.points.map((p) => p.age_days) ?? [];
  const allGrinds = params?.points.flatMap((p) => [p.grind, p.grind_predicted]) ?? [];
  const xDomain: [number, number] | undefined =
    x1Values.length > 0 ? [Math.min(...x1Values), Math.max(...x1Values)] : undefined;
  const yDomain: [number, number] | undefined =
    allGrinds.length > 0
      ? [Math.floor(Math.min(...allGrinds)) - 1, Math.ceil(Math.max(...allGrinds)) + 1]
      : undefined;

  const meanTempOffset =
    params && params.points.length > 0
      ? params.points.reduce((s, p) => s + p.temp_offset, 0) / params.points.length
      : 0;
  const x1Min = x1Values.length > 0 ? Math.min(...x1Values) : 0;
  const x1Max = x1Values.length > 0 ? Math.max(...x1Values) : 1;
  const fitLinePoints =
    params && coffeeIntercept !== null
      ? Array.from({ length: 100 }, (_, i) => {
          const t = i / 99;
          const xi = x1Min + t * (x1Max - x1Min);
          return { x: xi, y: params.a0 * meanTempOffset + params.a4 * xi + coffeeIntercept };
        })
      : [];

  // Plot 2 — temperature sensitivity
  const tempXDomain: [number, number] | undefined =
    tempNum !== null ? [tempNum - 5, tempNum + 5] : undefined;
  const tempYDomain: [number, number] | undefined =
    predicted !== null ? [predicted - 2, predicted + 2] : undefined;
  const tempLineData =
    params && coffeeIntercept !== null && ageDays !== null && tempNum !== null
      ? Array.from({ length: 100 }, (_, i) => {
          const T = tempNum - 5 + (i / 99) * 10;
          return { x: T, y: params.a0 * (T - 65) + params.a4 * ageDays + coffeeIntercept };
        })
      : [];

  // Plot 3 — histogram of coffee intercepts
  const histBins = params ? buildHistBins(params.coffee_intercepts, coffeeIntercept) : [];

  return (
    <Stack>
      <Title order={2}>Shot Planner</Title>

      <Group align="flex-end" gap="md">
        <Select
          label="Grinder"
          placeholder="Select a grinder…"
          data={grinderData}
          value={grinderId}
          onChange={setGrinderId}
          searchable
          clearable
          style={{ flex: 1 }}
        />
        <Select
          label="Coffee"
          placeholder="Select a coffee…"
          data={coffeeData}
          value={coffeeId}
          onChange={setCoffeeId}
          searchable
          clearable
          style={{ flex: 1 }}
        />
      </Group>

      {grinderId && (
        <Group align="center">
          <Button size="sm" variant="light" loading={retraining} onClick={handleRetrain}>
            Retrain Model
          </Button>
          {retrainError && (
            <Text size="sm" c="red">
              {retrainError}
            </Text>
          )}
        </Group>
      )}

      {loadingModel && (
        <Group justify="center" mt="md">
          <Loader size="sm" />
        </Group>
      )}

      {modelError && (
        <Text c="red" size="sm" mt="xs">
          {modelError}
        </Text>
      )}

      {params && (
        <>
          <Card
            shadow="sm"
            padding="md"
            withBorder
            style={{ backgroundColor: "var(--mantine-color-default-hover)" }}
          >
            <Stack gap="xs">
              {selectedCoffee?.roast_date && ageDays !== null && (
                <Text size="sm" c="dimmed">
                  Today is <strong>{ageDays}</strong> days since roast ({selectedCoffee.roast_date})
                </Text>
              )}
              <NumberInput
                label="Grinder Temperature (°F)"
                decimalScale={1}
                step={1}
                value={temp}
                onChange={setTemp}
                w={220}
              />
              {predicted !== null ? (
                <Group align="baseline" gap="xs" mt="xs">
                  <Text size="sm" c="dimmed">
                    Recommended grind:
                  </Text>
                  <Text fw={700} size="xl">
                    {formatGrind(predicted)}
                  </Text>
                  {params.r_squared !== null && (
                    <Text size="xs" c="dimmed">
                      R² = {params.r_squared.toFixed(2)}
                    </Text>
                  )}
                </Group>
              ) : (
                <Text size="sm" c="dimmed" mt="xs">
                  {!coffeeId
                    ? "Select a coffee to see a grind prediction."
                    : coffeeIntercept === null
                    ? "This coffee is not in the trained model. Retrain to include it."
                    : "Enter a temperature to see a prediction."}
                </Text>
              )}
              {targetTime != null && (
                <Group align="baseline" gap="xs">
                  <Text size="sm" c="dimmed">
                    Target shot time:
                  </Text>
                  <Text fw={700} size="xl">
                    {targetTime.toFixed(1)}s
                  </Text>
                </Group>
              )}
            </Stack>
          </Card>

          <Stack gap="xs">
            <Title order={4}>Model Details</Title>
            <Text size="sm" c="dimmed" style={{ fontFamily: "monospace" }}>
              grind = c(coffee) {fmtTerm(params.a0, "(temp − 65)")}{" "}
              {fmtTerm(params.a4, "age_days")} {fmtTerm(params.a2, "(time − target)")}{" "}
              {fmtTerm(params.a3, "(dose − 20)")} {fmtTerm(params.a5, "(yield − 2·dose)")}
            </Text>
            <Group gap="xl">
              <Text size="xs" c="dimmed">
                {params.n_shots_used} / {params.n_shots_available} shots used
              </Text>
              <Text size="xs" c="dimmed">
                {params.n_coffees} coffees
              </Text>
              <Text size="xs" c="dimmed">
                {params.converged ? "converged" : "did not converge"} in {params.n_iterations}{" "}
                iterations
              </Text>
              {params.r_squared !== null && (
                <Text size="xs" c="dimmed">
                  R² = {params.r_squared.toFixed(3)}
                </Text>
              )}
            </Group>
            <ResponsiveContainer width="100%" height={250}>
              <ComposedChart margin={{ top: 5, right: 20, bottom: 25, left: 60 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  type="number"
                  dataKey="x"
                  domain={xDomain}
                  label={{ value: "Days since roast", position: "insideBottom", offset: -10 }}
                  tickFormatter={(v) => Math.round(v).toString()}
                />
                <YAxis
                  type="number"
                  dataKey="y"
                  domain={yDomain}
                  tickFormatter={(v) => formatGrind(v as number)}
                  width={55}
                />
                <Tooltip formatter={(v) => formatGrind(v as number)} />
                <Legend verticalAlign="top" />
                <Scatter
                  name="Actual"
                  data={params.points.map((p) => ({ x: p.age_days, y: p.grind }))}
                  fill="#895d2b"
                />
                <Scatter
                  name="Predicted"
                  data={params.points.map((p) => ({ x: p.age_days, y: p.grind_predicted }))}
                  fill="#adb5bd"
                />
                {fitLinePoints.length > 0 && (
                  <Line
                    name="Fit"
                    data={fitLinePoints}
                    dataKey="y"
                    stroke="#c08858"
                    strokeWidth={2}
                    dot={false}
                    activeDot={false}
                    legendType="line"
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </Stack>

          {tempNum !== null && predicted !== null && (
            <Stack gap="xs">
              <Title order={4}>Temperature Sensitivity (Today)</Title>
              <ResponsiveContainer width="100%" height={200}>
                <ComposedChart margin={{ top: 5, right: 20, bottom: 25, left: 60 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    type="number"
                    dataKey="x"
                    domain={tempXDomain}
                    label={{
                      value: "Grinder Temperature (°F)",
                      position: "insideBottom",
                      offset: -10,
                    }}
                    tickFormatter={(v) => `${(v as number).toFixed(1)}°F`}
                  />
                  <YAxis
                    type="number"
                    dataKey="y"
                    domain={tempYDomain}
                    tickFormatter={(v) => formatGrind(v as number)}
                    width={55}
                  />
                  <Tooltip
                    formatter={(v) => formatGrind(v as number)}
                    labelFormatter={(l) => `${(l as number).toFixed(1)}°F`}
                  />
                  <Legend verticalAlign="top" />
                  <Line
                    name="Grind vs Temperature"
                    data={tempLineData}
                    dataKey="y"
                    stroke="#c08858"
                    strokeWidth={2}
                    dot={false}
                    activeDot={false}
                    legendType="line"
                  />
                  <Scatter
                    name="Selected"
                    data={[{ x: tempNum, y: predicted }]}
                    fill="#fa5252"
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </Stack>
          )}

          {histBins.length > 0 && (
            <Stack gap="xs">
              <Title order={4}>Coffee Intercept Distribution</Title>
              <Text size="xs" c="dimmed">
                Baseline grind setting c(coffee) for each coffee in the model.
                {coffeeIntercept !== null && (
                  <> Highlighted bar is the currently selected coffee ({formatGrind(coffeeIntercept)}).</>
                )}
              </Text>
              <ResponsiveContainer width="80%" height={400}>
                <BarChart data={histBins} margin={{ top: 5, right: 20, bottom: 50, left: 50 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="label"
                    label={{
                      value: "Grind Setting",
                      position: "insideBottom",
                      offset: -35,
                    }}
                    tick={{ angle: -35, textAnchor: "end" }}
                    height={55}
                  />
                  <YAxis
                    allowDecimals={false}
                    width={45}
                    label={{ value: "Coffees", angle: -90, position: "insideLeft", offset: 15 }}
                  />
                  <Tooltip content={<HistTooltipContent />} />
                  <Bar dataKey="count" name="Coffees" isAnimationActive={false}>
                    {histBins.map((bin, i) => (
                      <Cell key={i} fill={bin.hasSelected ? "#c08858" : "#adb5bd"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Stack>
          )}
        </>
      )}
    </Stack>
  );
}

import {
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
  CartesianGrid,
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
import { getGrindRegression } from "../api/reports";
import type {
  Coffee,
  Grinder,
  GrindRegressionGrinder,
  GrindRegressionResult,
} from "../types";

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

export default function ShotPlannerPage() {
  const [coffees, setCoffees] = useState<Coffee[]>([]);
  const [grinders, setGrinders] = useState<Grinder[]>([]);
  const [coffeeId, setCoffeeId] = useState<string | null>(null);
  const [grinderId, setGrinderId] = useState<string | null>(null);
  const [regression, setRegression] = useState<GrindRegressionResult | null>(null);
  const [regressionError, setRegressionError] = useState<string | null>(null);
  const [loadingRegression, setLoadingRegression] = useState(false);
  const [temp, setTemp] = useState<number | string>(64);

  useEffect(() => {
    Promise.all([getCoffees(), getGrinders()]).then(([c, g]) => {
      setCoffees(c);
      setGrinders(g);
    });
  }, []);

  useEffect(() => {
    if (!coffeeId) {
      setRegression(null);
      setRegressionError(null);
      return;
    }
    setLoadingRegression(true);
    setRegression(null);
    setRegressionError(null);
    getGrindRegression(Number(coffeeId), grinderId ? Number(grinderId) : undefined)
      .then((r) => {
        setRegression(r);
        setRegressionError(null);
      })
      .catch((err) => {
        setRegression(null);
        const status = err?.response?.status;
        if (status === 422) {
          setRegressionError(
            "Not enough shots with grind settings and temperatures recorded for this coffee/grinder combination."
          );
        } else if (status === 404) {
          setRegressionError("Coffee not found or has no roast date.");
        } else {
          setRegressionError("Failed to load regression data.");
        }
      })
      .finally(() => setLoadingRegression(false));
  }, [coffeeId, grinderId]);

  const coffeeData = coffees.map((c) => ({
    value: String(c.id),
    label: `${c.name} — ${c.roaster}${c.roast_date ? ` (${c.roast_date})` : ""}`,
  }));

  const grinderData = grinders.map((g) => ({
    value: String(g.id),
    label: `${g.make} ${g.model}`,
  }));

  const grinderResult: GrindRegressionGrinder | undefined = regression?.grinders[0];

  const x1 = regression ? daysSince(regression.roast_date) : null;
  const x2 = typeof temp === "number" ? temp - 65 : null;
  const predicted =
    grinderResult && x1 !== null && x2 !== null
      ? grinderResult.coefficients.a * x1 +
        grinderResult.coefficients.b * x2 +
        grinderResult.coefficients.c
      : null;

  const firstY = grinderResult?.points[0]?.y ?? 87;
  const yDomain: [number, number] = [firstY - 2, firstY + 2];
  const x1Values = grinderResult?.points.map((p) => p.x1) ?? [];
  const xDomain: [number, number] | undefined =
    x1Values.length > 0 ? [Math.min(...x1Values), Math.max(...x1Values)] : undefined;

  const { a, b, c } = grinderResult?.coefficients ?? { a: 0, b: 0, c: 0 };
  const signB = b >= 0 ? "+" : "−";
  const signC = c >= 0 ? "+" : "−";

  // Fit line for Model Details: project 2D regression onto days axis using mean x2
  const meanX2 = grinderResult
    ? grinderResult.points.reduce((sum, p) => sum + p.x2, 0) / grinderResult.points.length
    : 0;
  const x1Min = x1Values.length > 0 ? Math.min(...x1Values) : 0;
  const x1Max = x1Values.length > 0 ? Math.max(...x1Values) : 1;
  const fitLinePoints = grinderResult
    ? Array.from({ length: 100 }, (_, i) => {
        const t = i / 99;
        const xi = x1Min + t * (x1Max - x1Min);
        return { x: xi, y: a * xi + b * meanX2 + c };
      })
    : [];

  // Temperature sensitivity chart — today's grind setting across ±5 °F
  const tempNum = typeof temp === "number" ? temp : null;
  const tempXDomain: [number, number] | undefined =
    tempNum !== null ? [tempNum - 5, tempNum + 5] : undefined;
  const tempYDomain: [number, number] | undefined =
    predicted !== null ? [predicted - 2, predicted + 2] : undefined;

  return (
    <Stack>
      <Title order={2}>Shot Planner</Title>

      <Group align="flex-end" gap="md">
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
        <Select
          label="Grinder"
          placeholder="Default (Mazzer)"
          data={grinderData}
          value={grinderId}
          onChange={setGrinderId}
          searchable
          clearable
          style={{ flex: 1 }}
        />
      </Group>

      {loadingRegression && (
        <Group justify="center" mt="md">
          <Loader size="sm" />
        </Group>
      )}

      {regressionError && (
        <Text c="red" size="sm" mt="xs">
          {regressionError}
        </Text>
      )}

      {grinderResult && (
        <>
          <Card
            shadow="sm"
            padding="md"
            withBorder
            style={{ backgroundColor: "var(--mantine-color-default-hover)" }}
          >
            <Stack gap="xs">
              <Text size="sm" c="dimmed">
                Today is{" "}
                <strong>{x1}</strong> days since roast ({regression!.roast_date})
              </Text>
              <NumberInput
                label="Grinder Temperature (°F)"
                decimalScale={1}
                step={1}
                value={temp}
                onChange={setTemp}
                w={220}
              />
              {predicted !== null && (
                <Group align="baseline" gap="xs" mt="xs">
                  <Text size="sm" c="dimmed">Recommended grind:</Text>
                  <Text fw={700} size="xl">
                    {formatGrind(predicted)}
                  </Text>
                  {grinderResult.r_squared !== null && (
                    <Text size="xs" c="dimmed">
                      R² = {grinderResult.r_squared.toFixed(2)}
                    </Text>
                  )}
                </Group>
              )}
              {regression?.target_shot_time != null && (
                <Group align="baseline" gap="xs">
                  <Text size="sm" c="dimmed">Target shot time:</Text>
                  <Text fw={700} size="xl">
                    {regression.target_shot_time.toFixed(1)}s
                  </Text>
                </Group>
              )}
            </Stack>
          </Card>

          <Stack gap="xs">
            <Title order={4}>Model Details</Title>
            <Text size="sm" c="dimmed">
              y = {a.toFixed(4)} · (days since roast) {signB} {Math.abs(b).toFixed(4)} · (temp − 65){" "}
              {signC} {Math.abs(c).toFixed(4)}
            </Text>
            <Text size="xs" c="dimmed">
              Based on {grinderResult.n_shots} shots with {grinderResult.grinder_label}
            </Text>
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
                <Scatter name="Actual" data={grinderResult.points.map((p) => ({ x: p.x1, y: p.y }))} fill="#895d2b" />
                <Scatter name="Predicted" data={grinderResult.points.map((p) => ({ x: p.x1, y: p.y_predicted }))} fill="#adb5bd" />
                <Line name="Fit" data={fitLinePoints} dataKey="y" stroke="#c08858" strokeWidth={2} dot={false} activeDot={false} legendType="line" />
              </ComposedChart>
            </ResponsiveContainer>
          </Stack>

          {grinderResult && tempNum !== null && predicted !== null && (
            <Stack gap="xs">
              <Title order={4}>Temperature Sensitivity (Today)</Title>
              <ResponsiveContainer width="100%" height={200}>
                <ComposedChart margin={{ top: 5, right: 20, bottom: 25, left: 60 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    type="number"
                    dataKey="x"
                    domain={tempXDomain}
                    label={{ value: "Grinder Temperature (°F)", position: "insideBottom", offset: -10 }}
                    tickFormatter={(v) => `${(v as number).toFixed(1)}°F`}
                  />
                  <YAxis
                    type="number"
                    dataKey="y"
                    domain={tempYDomain}
                    tickFormatter={(v) => formatGrind(v as number)}
                    width={55}
                  />
                  <Tooltip formatter={(v) => formatGrind(v as number)} labelFormatter={(l) => `${(l as number).toFixed(1)}°F`} />
                  <Legend verticalAlign="top" />
                  <Line name="Grind vs Temperature" data={tempNum !== null && x1 !== null ? Array.from({ length: 100 }, (_, i) => { const T = tempNum - 5 + (i / 99) * 10; return { x: T, y: a * x1 + b * (T - 65) + c }; }) : []} dataKey="y" stroke="#c08858" strokeWidth={2} dot={false} activeDot={false} legendType="line" />
                  <Scatter name="Selected" data={tempNum !== null && predicted !== null ? [{ x: tempNum, y: predicted }] : []} fill="#fa5252" />
                </ComposedChart>
              </ResponsiveContainer>
            </Stack>
          )}
        </>
      )}
    </Stack>
  );
}

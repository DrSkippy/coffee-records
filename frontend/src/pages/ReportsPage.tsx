import { BarChart, LineChart } from "@mantine/charts";
import { Group, Select, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { useEffect, useState } from "react";
import {
  getDoseYield,
  getExtractionTrends,
  getShotsPerDay,
} from "../api/reports";
import { getCoffees } from "../api/coffees";
import { getBrewingDevices, getGrinders } from "../api/equipment";
import type {
  BrewingDevice,
  Coffee,
  DoseYieldPoint,
  ExtractionPoint,
  Grinder,
  ShotsPerDayPoint,
} from "../types";

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

export default function ReportsPage() {
  const [days, setDays] = useState("30");
  const [coffeeId, setCoffeeId] = useState<string | null>(null);
  const [grinderId, setGrinderId] = useState<string | null>(null);
  const [deviceId, setDeviceId] = useState<string | null>(null);

  const [coffees, setCoffees] = useState<Coffee[]>([]);
  const [grinders, setGrinders] = useState<Grinder[]>([]);
  const [devices, setDevices] = useState<BrewingDevice[]>([]);

  const [doseYield, setDoseYield] = useState<DoseYieldPoint[]>([]);
  const [perDay, setPerDay] = useState<ShotsPerDayPoint[]>([]);
  const [extraction, setExtraction] = useState<ExtractionPoint[]>([]);

  // Load filter options once
  useEffect(() => {
    getCoffees().then(setCoffees);
    getGrinders().then(setGrinders);
    getBrewingDevices().then(setDevices);
  }, []);

  // Reload charts whenever any filter changes
  useEffect(() => {
    const params = {
      date_from: daysAgo(Number(days)),
      date_to: new Date().toISOString().slice(0, 10),
      ...(coffeeId ? { coffee_id: Number(coffeeId) } : {}),
      ...(grinderId ? { grinder_id: Number(grinderId) } : {}),
      ...(deviceId ? { device_id: Number(deviceId) } : {}),
    };
    getDoseYield(params).then(setDoseYield);
    getShotsPerDay(params).then(setPerDay);
    getExtractionTrends(params).then(setExtraction);
  }, [days, coffeeId, grinderId, deviceId]);

  const coffeeOptions = coffees.map((c) => ({
    value: String(c.id),
    label: `${c.roaster} — ${c.name}`,
  }));
  const grinderOptions = grinders.map((g) => ({
    value: String(g.id),
    label: `${g.make} ${g.model}`,
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
          label="Grinder"
          data={grinderOptions}
          value={grinderId}
          onChange={setGrinderId}
          placeholder="All grinders"
          clearable
          w={200}
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
              data={extraction}
              dataKey="date"
              series={[{ name: "extraction_time", color: "coffee.6", label: "Seconds" }]}
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
              data={doseYield}
              dataKey="date"
              series={[{ name: "ratio", color: "coffee.5", label: "Ratio" }]}
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
              data={doseYield}
              dataKey="date"
              series={[
                { name: "dose_weight", color: "coffee.7", label: "Dose (g)" },
                { name: "final_weight", color: "coffee.9", label: "Yield (g)" },
              ]}
              curveType="monotone"
            />
          )}
        </Stack>
      </SimpleGrid>
    </Stack>
  );
}

import { BarChart, LineChart } from "@mantine/charts";
import { Group, Select, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { useEffect, useState } from "react";
import {
  getDoseYield,
  getExtractionTrends,
  getShotsPerDay,
} from "../api/reports";
import type { DoseYieldPoint, ExtractionPoint, ShotsPerDayPoint } from "../types";

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
  const [doseYield, setDoseYield] = useState<DoseYieldPoint[]>([]);
  const [perDay, setPerDay] = useState<ShotsPerDayPoint[]>([]);
  const [extraction, setExtraction] = useState<ExtractionPoint[]>([]);

  useEffect(() => {
    const params = { date_from: daysAgo(Number(days)), date_to: new Date().toISOString().slice(0, 10) };
    getDoseYield(params).then(setDoseYield);
    getShotsPerDay(params).then(setPerDay);
    getExtractionTrends(params).then(setExtraction);
  }, [days]);

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Reports</Title>
        <Select
          data={DATE_RANGES}
          value={days}
          onChange={(v) => setDays(v ?? "30")}
          w={160}
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
              series={[{ name: "count", color: "blue.6", label: "Shots" }]}
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
              series={[{ name: "extraction_time", color: "orange.6", label: "Seconds" }]}
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
              series={[{ name: "ratio", color: "green.6", label: "Ratio" }]}
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
                { name: "dose_weight", color: "violet.6", label: "Dose (g)" },
                { name: "final_weight", color: "teal.6", label: "Yield (g)" },
              ]}
              curveType="monotone"
            />
          )}
        </Stack>
      </SimpleGrid>
    </Stack>
  );
}

import { Badge, Card, Group, Stack, Text } from "@mantine/core";
import type { Shot } from "../../types";

export default function ShotCard({ shot }: { shot: Shot }) {
  const flags = [
    shot.wedge && "Wedge",
    shot.shaker && "Shaker",
    shot.wdt && "WDT",
    shot.flow_taper && "Flow Taper",
  ].filter(Boolean) as string[];

  return (
    <Card shadow="sm" padding="sm" withBorder mb="xs">
      <Group justify="space-between" mb="xs">
        <Text fw={600}>{shot.date}</Text>
        <Badge color={shot.maker === "Scott" ? "blue" : "grape"}>
          {shot.maker}
        </Badge>
      </Group>
      <Stack gap={4}>
        {shot.coffee_name && <Text size="sm">Coffee: {shot.coffee_name}</Text>}
        {shot.drink_type && (
          <Text size="sm" tt="capitalize">
            Drink: {shot.drink_type}
          </Text>
        )}
        <Group gap="xs">
          {shot.dose_weight != null && (
            <Text size="sm">{shot.dose_weight}g in</Text>
          )}
          {shot.final_weight != null && (
            <Text size="sm">{shot.final_weight}g out</Text>
          )}
          {shot.extraction_time != null && (
            <Text size="sm">{shot.extraction_time}s</Text>
          )}
        </Group>
        {shot.grinder_label && (
          <Text size="sm" c="dimmed">
            Grinder: {shot.grinder_label}
          </Text>
        )}
        {shot.device_label && (
          <Text size="sm" c="dimmed">
            Machine: {shot.device_label}
          </Text>
        )}
        {flags.length > 0 && (
          <Group gap={4}>
            {flags.map((f) => (
              <Badge key={f} size="xs" variant="outline">
                {f}
              </Badge>
            ))}
          </Group>
        )}
        {shot.notes && (
          <Text size="xs" c="dimmed" fs="italic">
            {shot.notes}
          </Text>
        )}
      </Stack>
    </Card>
  );
}

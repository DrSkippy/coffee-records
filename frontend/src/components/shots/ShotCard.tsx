import { ActionIcon, Badge, Box, Card, Group, Stack, Text, Tooltip } from "@mantine/core";
import { IconChartLine, IconPencil, IconVideo } from "@tabler/icons-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Shot } from "../../types";
import TelemetryModal from "./TelemetryModal";

const VIDEO_BASE_URL = "https://resources.drskippy.app/coffee";

export default function ShotCard({ shot }: { shot: Shot }) {
  const navigate = useNavigate();
  const [telemetryOpen, setTelemetryOpen] = useState(false);
  const flags = [
    shot.wedge && "Wedge",
    shot.shaker && "Shaker",
    shot.wdt && "WDT",
    shot.flow_taper && "Flow Taper",
  ].filter(Boolean) as string[];

  const hasGrindPanel =
    shot.grind_setting != null ||
    shot.grinder_temp_before != null ||
    shot.grinder_temp_after != null;

  return (
    <Card shadow="sm" padding="sm" withBorder mb="xs">
      <Group justify="space-between" mb="xs">
        <Group gap={6}>
          <Text fw={600}>{shot.date}</Text>
          <Text size="xs" c="dimmed">#{shot.id}</Text>
        </Group>
        <Group gap="xs">
          {shot.video_filename && (
            <Tooltip label="Watch video">
              <ActionIcon
                component="a"
                href={`${VIDEO_BASE_URL}/${shot.video_filename}`}
                target="_blank"
                variant="subtle"
                size="sm"
              >
                <IconVideo size={16} />
              </ActionIcon>
            </Tooltip>
          )}
          {shot.telemetry_filename && (
            <Tooltip label="Shot telemetry">
              <ActionIcon
                variant="subtle"
                size="sm"
                onClick={() => setTelemetryOpen(true)}
              >
                <IconChartLine size={16} />
              </ActionIcon>
            </Tooltip>
          )}
          <Tooltip label="Edit shot">
            <ActionIcon
              variant="subtle"
              size="sm"
              onClick={() => navigate(`/shots/${shot.id}/edit`)}
            >
              <IconPencil size={16} />
            </ActionIcon>
          </Tooltip>
          <Badge color="coffee.7">{shot.maker}</Badge>
        </Group>
      </Group>

      <Group align="flex-start" wrap="nowrap" gap="sm">
        <Stack gap={4} style={{ flex: 1, minWidth: 0 }}>
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

        {hasGrindPanel && (
          <Box
            p="xs"
            style={{
              backgroundColor: "var(--mantine-color-default-hover)",
              borderRadius: "var(--mantine-radius-sm)",
              minWidth: 110,
              flexShrink: 0,
            }}
          >
            <Stack gap={4}>
              {shot.grind_setting != null && (
                <>
                  <Text size="xs" c="dimmed" fw={600}>Grind</Text>
                  <Text size="sm">{shot.grind_setting}</Text>
                </>
              )}
              {shot.grinder_temp_before != null && (
                <>
                  <Text size="xs" c="dimmed" fw={600}>Temp before</Text>
                  <Text size="sm">{shot.grinder_temp_before}°F</Text>
                </>
              )}
              {shot.grinder_temp_after != null && (
                <>
                  <Text size="xs" c="dimmed" fw={600}>Temp after</Text>
                  <Text size="sm">{shot.grinder_temp_after}°F</Text>
                </>
              )}
            </Stack>
          </Box>
        )}
      </Group>
      {shot.telemetry_filename && (
        <TelemetryModal
          shot={shot}
          opened={telemetryOpen}
          onClose={() => setTelemetryOpen(false)}
        />
      )}
    </Card>
  );
}

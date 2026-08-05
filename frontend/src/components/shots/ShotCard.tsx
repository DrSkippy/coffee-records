import {
  ActionIcon,
  Badge,
  Box,
  Card,
  Group,
  Image,
  Modal,
  Stack,
  Text,
  Tooltip,
  UnstyledButton,
} from "@mantine/core";
import { IconChartLine, IconPencil, IconVideo } from "@tabler/icons-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { coffeeResourceUrl, telemetryResourceUrl } from "../../api/resources";
import type { Shot } from "../../types";
import TelemetryModal from "./TelemetryModal";

export default function ShotCard({ shot }: { shot: Shot }) {
  const navigate = useNavigate();
  const [telemetryOpen, setTelemetryOpen] = useState(false);
  const [coffeeOpen, setCoffeeOpen] = useState(false);
  const [thumbnailFailed, setThumbnailFailed] = useState(false);
  const coffeeImageUrl = shot.coffee_image_filename
    ? coffeeResourceUrl(shot.coffee_image_filename)
    : null;
  const telemetryThumbnailUrl = shot.telemetry_thumbnail_filename
    ? telemetryResourceUrl(shot.telemetry_thumbnail_filename)
    : null;
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
      <Group justify="space-between" mb="xs" wrap="nowrap">
        <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
          {coffeeImageUrl && (
            <Tooltip label={`View ${shot.coffee_name ?? "coffee"} photo`}>
              <UnstyledButton
                onClick={() => setCoffeeOpen(true)}
                aria-label={`View ${shot.coffee_name ?? "coffee"} photo`}
                style={{ flexShrink: 0, height: 28 }}
              >
                <Image src={coffeeImageUrl} alt="" w={28} h={28} fit="cover" radius="sm" />
              </UnstyledButton>
            </Tooltip>
          )}
          <Text fw={600} truncate>{shot.date}</Text>
          <Text size="xs" c="dimmed">#{shot.id}</Text>
        </Group>
        <Group gap="xs" wrap="nowrap">
          {shot.video_filename && (
            <Tooltip label="Watch video">
              <ActionIcon
                component="a"
                href={coffeeResourceUrl(shot.video_filename)}
                target="_blank"
                variant="subtle"
                size="sm"
              >
                <IconVideo size={16} />
              </ActionIcon>
            </Tooltip>
          )}
          {shot.telemetry_filename && telemetryThumbnailUrl && !thumbnailFailed ? (
            <Tooltip label="Open shot telemetry">
              <UnstyledButton
                onClick={() => setTelemetryOpen(true)}
                aria-label="Open shot telemetry"
                style={{ flexShrink: 0, width: "clamp(56px, 16vw, 84px)", height: 28 }}
              >
                <Image
                  src={telemetryThumbnailUrl}
                  alt=""
                  w="100%"
                  h={28}
                  fit="contain"
                  radius="sm"
                  onError={() => setThumbnailFailed(true)}
                />
              </UnstyledButton>
            </Tooltip>
          ) : shot.telemetry_filename ? (
            <Tooltip label="Shot telemetry">
              <ActionIcon variant="subtle" size="sm" onClick={() => setTelemetryOpen(true)}>
                <IconChartLine size={16} />
              </ActionIcon>
            </Tooltip>
          ) : null}
          <Tooltip label="Edit shot">
            <ActionIcon variant="subtle" size="sm" onClick={() => navigate(`/shots/${shot.id}/edit`)}>
              <IconPencil size={16} />
            </ActionIcon>
          </Tooltip>
          <Badge color="coffee.7">{shot.maker}</Badge>
        </Group>
      </Group>

      <Group align="flex-start" wrap="nowrap" gap="sm">
        <Stack gap={4} style={{ flex: 1, minWidth: 0 }}>
          {shot.coffee_name && <Text size="sm">Coffee: {shot.coffee_name}</Text>}
          {shot.drink_type && <Text size="sm" tt="capitalize">Drink: {shot.drink_type}</Text>}
          <Group gap="xs">
            {shot.dose_weight != null && <Text size="sm">{shot.dose_weight}g in</Text>}
            {shot.final_weight != null && <Text size="sm">{shot.final_weight}g out</Text>}
            {shot.extraction_time != null && <Text size="sm">{shot.extraction_time}s</Text>}
          </Group>
          {shot.grinder_label && <Text size="sm" c="dimmed">Grinder: {shot.grinder_label}</Text>}
          {shot.device_label && <Text size="sm" c="dimmed">Machine: {shot.device_label}</Text>}
          {flags.length > 0 && (
            <Group gap={4}>
              {flags.map((flag) => <Badge key={flag} size="xs" variant="outline">{flag}</Badge>)}
            </Group>
          )}
          {shot.notes && <Text size="xs" c="dimmed" fs="italic">{shot.notes}</Text>}
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
                <><Text size="xs" c="dimmed" fw={600}>Grind</Text><Text size="sm">{shot.grind_setting}</Text></>
              )}
              {shot.grinder_temp_before != null && (
                <><Text size="xs" c="dimmed" fw={600}>Temp before</Text><Text size="sm">{shot.grinder_temp_before}°F</Text></>
              )}
              {shot.grinder_temp_after != null && (
                <><Text size="xs" c="dimmed" fw={600}>Temp after</Text><Text size="sm">{shot.grinder_temp_after}°F</Text></>
              )}
            </Stack>
          </Box>
        )}
      </Group>

      {coffeeImageUrl && (
        <Modal
          opened={coffeeOpen}
          onClose={() => setCoffeeOpen(false)}
          title={shot.coffee_name ?? "Coffee photo"}
          size="auto"
          centered
          styles={{ body: { padding: 0 }, content: { maxWidth: "min(90vw, 600px)", width: "100%" } }}
        >
          <Image
            src={coffeeImageUrl}
            alt={shot.coffee_name ?? "Coffee"}
            fit="contain"
            style={{ maxHeight: "80vh", width: "100%", display: "block" }}
          />
        </Modal>
      )}
      {shot.telemetry_filename && (
        <TelemetryModal shot={shot} opened={telemetryOpen} onClose={() => setTelemetryOpen(false)} />
      )}
    </Card>
  );
}

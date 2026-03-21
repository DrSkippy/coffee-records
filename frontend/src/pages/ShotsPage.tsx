import { Button, Group, Select, Stack, Text, Title } from "@mantine/core";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getShots } from "../api/shots";
import ShotCard from "../components/shots/ShotCard";
import type { Shot } from "../types";

export default function ShotsPage() {
  const [shots, setShots] = useState<Shot[]>([]);
  const [makerFilter, setMakerFilter] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    setLoading(true);
    getShots({ maker: makerFilter ?? undefined, limit: 50 })
      .then(setShots)
      .finally(() => setLoading(false));
  }, [makerFilter]);

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Shots</Title>
        <Button onClick={() => navigate("/shots/new")}>+ New Shot</Button>
      </Group>
      <Group>
        <Select
          placeholder="All makers"
          data={["Scott", "Sara"]}
          value={makerFilter}
          onChange={setMakerFilter}
          clearable
          w={160}
        />
      </Group>
      {loading ? (
        <Text>Loading...</Text>
      ) : shots.length === 0 ? (
        <Text c="dimmed">No shots logged yet.</Text>
      ) : (
        shots.map((s) => <ShotCard key={s.id} shot={s} />)
      )}
    </Stack>
  );
}

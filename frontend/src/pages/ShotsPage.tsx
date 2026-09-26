import { Button, FileButton, Group, Select, Stack, Text, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconFileImport } from "@tabler/icons-react";
import { isAxiosError } from "axios";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getShots, importShotCsv } from "../api/shots";
import ShotCard from "../components/shots/ShotCard";
import type { Shot } from "../types";

export default function ShotsPage() {
  const [shots, setShots] = useState<Shot[]>([]);
  const [makerFilter, setMakerFilter] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const navigate = useNavigate();

  const handleMakerChange = (value: string | null) => {
    setLoading(true);
    setMakerFilter(value);
  };

  const handleImportCsv = async (file: File | null) => {
    if (!file) return;
    setImporting(true);
    try {
      const csvImport = await importShotCsv(file);
      navigate("/shots/new", { state: { csvImport } });
    } catch (e) {
      const message =
        (isAxiosError(e) && e.response?.data?.error) || "Failed to import CSV";
      notifications.show({ message, color: "red" });
    } finally {
      setImporting(false);
    }
  };

  useEffect(() => {
    getShots({ maker: makerFilter ?? undefined, limit: 50 })
      .then(setShots)
      .finally(() => setLoading(false));
  }, [makerFilter]);

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Shots</Title>
        <Group gap="xs">
          <FileButton onChange={handleImportCsv} accept=".csv,text/csv">
            {(props) => (
              <Button
                {...props}
                variant="light"
                loading={importing}
                leftSection={<IconFileImport size={16} />}
              >
                Import CSV
              </Button>
            )}
          </FileButton>
          <Button onClick={() => navigate("/shots/new")}>+ New Shot</Button>
        </Group>
      </Group>
      <Group>
        <Select
          placeholder="All makers"
          data={["Scott", "Sara"]}
          value={makerFilter}
          onChange={handleMakerChange}
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

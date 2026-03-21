import {
  ActionIcon,
  Button,
  Group,
  Modal,
  NumberInput,
  Select,
  Stack,
  Table,
  Tabs,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconPencil, IconTrash } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import {
  createBrewingDevice,
  createGrinder,
  createScale,
  deleteBrewingDevice,
  deleteGrinder,
  deleteScale,
  getBrewingDevices,
  getGrinders,
  getScales,
  updateBrewingDevice,
  updateGrinder,
  updateScale,
} from "../api/equipment";
import type { BrewingDevice, Grinder, Scale } from "../types";

function useEquipment() {
  const [grinders, setGrinders] = useState<Grinder[]>([]);
  const [devices, setDevices] = useState<BrewingDevice[]>([]);
  const [scales, setScales] = useState<Scale[]>([]);

  const reload = () =>
    Promise.all([getGrinders(), getBrewingDevices(), getScales()]).then(([g, d, s]) => {
      setGrinders(g);
      setDevices(d);
      setScales(s);
    });

  useEffect(() => { reload(); }, []);
  return { grinders, devices, scales, reload };
}

function confirmDelete(cb: () => Promise<unknown>, reload: () => void) {
  cb()
    .then(reload)
    .catch((err: unknown) => {
      const status = (err as { response?: { status: number } })?.response?.status;
      notifications.show({
        message: status === 409 ? "Cannot delete: shots reference this item" : "Delete failed",
        color: "red",
      });
    });
}

// ── Grinders Tab ─────────────────────────────────────────────────────────────

function GrindersTab({
  grinders,
  reload,
}: {
  grinders: Grinder[];
  reload: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Grinder | null>(null);
  const form = useForm({
    initialValues: { make: "", model: "", type: "flat", notes: "" },
  });

  const openCreate = () => {
    setEditing(null);
    form.reset();
    setOpen(true);
  };
  const openEdit = (g: Grinder) => {
    setEditing(g);
    form.setValues({ make: g.make, model: g.model, type: g.type, notes: g.notes ?? "" });
    setOpen(true);
  };
  const handleSubmit = async (v: typeof form.values) => {
    const payload = { ...v, notes: v.notes || null, type: v.type as Grinder["type"] };
    if (editing) await updateGrinder(editing.id, payload);
    else await createGrinder(payload);
    setOpen(false);
    reload();
  };

  return (
    <>
      <Group justify="flex-end" mb="sm">
        <Button size="sm" onClick={openCreate}>
          + Add Grinder
        </Button>
      </Group>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Make</Table.Th>
            <Table.Th>Model</Table.Th>
            <Table.Th>Type</Table.Th>
            <Table.Th>Notes</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {grinders.map((g) => (
            <Table.Tr key={g.id}>
              <Table.Td>{g.make}</Table.Td>
              <Table.Td>{g.model}</Table.Td>
              <Table.Td>{g.type}</Table.Td>
              <Table.Td>{g.notes ?? "—"}</Table.Td>
              <Table.Td>
                <Group gap="xs">
                  <ActionIcon variant="subtle" onClick={() => openEdit(g)}>
                    <IconPencil size={16} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    onClick={() => confirmDelete(() => deleteGrinder(g.id), reload)}
                  >
                    <IconTrash size={16} />
                  </ActionIcon>
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
          {grinders.length === 0 && (
            <Table.Tr>
              <Table.Td colSpan={5}>
                <Text c="dimmed" ta="center">No grinders yet</Text>
              </Table.Td>
            </Table.Tr>
          )}
        </Table.Tbody>
      </Table>
      <Modal opened={open} onClose={() => setOpen(false)} title={editing ? "Edit Grinder" : "Add Grinder"}>
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack>
            <TextInput label="Make" required {...form.getInputProps("make")} />
            <TextInput label="Model" required {...form.getInputProps("model")} />
            <Select
              label="Type"
              required
              data={["flat", "conical", "blade"]}
              {...form.getInputProps("type")}
            />
            <Textarea label="Notes" {...form.getInputProps("notes")} />
            <Button type="submit">{editing ? "Update" : "Create"}</Button>
          </Stack>
        </form>
      </Modal>
    </>
  );
}

// ── Brewing Devices Tab ───────────────────────────────────────────────────────

function DevicesTab({
  devices,
  reload,
}: {
  devices: BrewingDevice[];
  reload: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<BrewingDevice | null>(null);
  const form = useForm({
    initialValues: {
      make: "",
      model: "",
      type: "",
      warmup_minutes: "" as number | string,
      notes: "",
    },
  });

  const openCreate = () => {
    setEditing(null);
    form.reset();
    setOpen(true);
  };
  const openEdit = (d: BrewingDevice) => {
    setEditing(d);
    form.setValues({
      make: d.make,
      model: d.model,
      type: d.type,
      warmup_minutes: d.warmup_minutes ?? "",
      notes: d.notes ?? "",
    });
    setOpen(true);
  };
  const handleSubmit = async (v: typeof form.values) => {
    const payload = {
      ...v,
      warmup_minutes: v.warmup_minutes !== "" ? Number(v.warmup_minutes) : null,
      notes: v.notes || null,
    };
    if (editing) await updateBrewingDevice(editing.id, payload);
    else await createBrewingDevice(payload);
    setOpen(false);
    reload();
  };

  return (
    <>
      <Group justify="flex-end" mb="sm">
        <Button size="sm" onClick={openCreate}>
          + Add Machine
        </Button>
      </Group>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Make</Table.Th>
            <Table.Th>Model</Table.Th>
            <Table.Th>Type</Table.Th>
            <Table.Th>Warmup (min)</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {devices.map((d) => (
            <Table.Tr key={d.id}>
              <Table.Td>{d.make}</Table.Td>
              <Table.Td>{d.model}</Table.Td>
              <Table.Td>{d.type}</Table.Td>
              <Table.Td>{d.warmup_minutes ?? "—"}</Table.Td>
              <Table.Td>
                <Group gap="xs">
                  <ActionIcon variant="subtle" onClick={() => openEdit(d)}>
                    <IconPencil size={16} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    onClick={() => confirmDelete(() => deleteBrewingDevice(d.id), reload)}
                  >
                    <IconTrash size={16} />
                  </ActionIcon>
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
          {devices.length === 0 && (
            <Table.Tr>
              <Table.Td colSpan={5}>
                <Text c="dimmed" ta="center">No machines yet</Text>
              </Table.Td>
            </Table.Tr>
          )}
        </Table.Tbody>
      </Table>
      <Modal opened={open} onClose={() => setOpen(false)} title={editing ? "Edit Machine" : "Add Machine"}>
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack>
            <TextInput label="Make" required {...form.getInputProps("make")} />
            <TextInput label="Model" required {...form.getInputProps("model")} />
            <TextInput label="Type" required placeholder="espresso / drip / etc" {...form.getInputProps("type")} />
            <NumberInput label="Warmup (min)" decimalScale={1} {...form.getInputProps("warmup_minutes")} />
            <Textarea label="Notes" {...form.getInputProps("notes")} />
            <Button type="submit">{editing ? "Update" : "Create"}</Button>
          </Stack>
        </form>
      </Modal>
    </>
  );
}

// ── Scales Tab ────────────────────────────────────────────────────────────────

function ScalesTab({ scales, reload }: { scales: Scale[]; reload: () => void }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Scale | null>(null);
  const form = useForm({ initialValues: { make: "", model: "", notes: "" } });

  const openCreate = () => {
    setEditing(null);
    form.reset();
    setOpen(true);
  };
  const openEdit = (s: Scale) => {
    setEditing(s);
    form.setValues({ make: s.make, model: s.model, notes: s.notes ?? "" });
    setOpen(true);
  };
  const handleSubmit = async (v: typeof form.values) => {
    const payload = { ...v, notes: v.notes || null };
    if (editing) await updateScale(editing.id, payload);
    else await createScale(payload);
    setOpen(false);
    reload();
  };

  return (
    <>
      <Group justify="flex-end" mb="sm">
        <Button size="sm" onClick={openCreate}>
          + Add Scale
        </Button>
      </Group>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Make</Table.Th>
            <Table.Th>Model</Table.Th>
            <Table.Th>Notes</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {scales.map((s) => (
            <Table.Tr key={s.id}>
              <Table.Td>{s.make}</Table.Td>
              <Table.Td>{s.model}</Table.Td>
              <Table.Td>{s.notes ?? "—"}</Table.Td>
              <Table.Td>
                <Group gap="xs">
                  <ActionIcon variant="subtle" onClick={() => openEdit(s)}>
                    <IconPencil size={16} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    onClick={() => confirmDelete(() => deleteScale(s.id), reload)}
                  >
                    <IconTrash size={16} />
                  </ActionIcon>
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
          {scales.length === 0 && (
            <Table.Tr>
              <Table.Td colSpan={4}>
                <Text c="dimmed" ta="center">No scales yet</Text>
              </Table.Td>
            </Table.Tr>
          )}
        </Table.Tbody>
      </Table>
      <Modal opened={open} onClose={() => setOpen(false)} title={editing ? "Edit Scale" : "Add Scale"}>
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack>
            <TextInput label="Make" required {...form.getInputProps("make")} />
            <TextInput label="Model" required {...form.getInputProps("model")} />
            <Textarea label="Notes" {...form.getInputProps("notes")} />
            <Button type="submit">{editing ? "Update" : "Create"}</Button>
          </Stack>
        </form>
      </Modal>
    </>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function EquipmentPage() {
  const { grinders, devices, scales, reload } = useEquipment();

  return (
    <Stack>
      <Title order={2}>Equipment</Title>
      <Tabs defaultValue="grinders">
        <Tabs.List>
          <Tabs.Tab value="grinders">Grinders</Tabs.Tab>
          <Tabs.Tab value="machines">Machines</Tabs.Tab>
          <Tabs.Tab value="scales">Scales</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="grinders" pt="md">
          <GrindersTab grinders={grinders} reload={reload} />
        </Tabs.Panel>
        <Tabs.Panel value="machines" pt="md">
          <DevicesTab devices={devices} reload={reload} />
        </Tabs.Panel>
        <Tabs.Panel value="scales" pt="md">
          <ScalesTab scales={scales} reload={reload} />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}

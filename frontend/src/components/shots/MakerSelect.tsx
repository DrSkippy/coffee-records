import { Combobox, InputBase, useCombobox } from "@mantine/core";
import { IconUserPlus } from "@tabler/icons-react";
import { useState } from "react";
import { makerOptions } from "../../utils/makers";

const ADD_OPTION = "$add";

interface MakerSelectProps {
  value?: string;
  onChange: (value: string) => void;
  knownMakers?: string[];
  label?: string;
  required?: boolean;
  error?: React.ReactNode;
}

/** Maker dropdown: Scott, Sara and past makers, plus typing a new name to add someone. */
export default function MakerSelect({
  value = "",
  onChange,
  knownMakers = [],
  label = "Maker",
  required,
  error,
}: MakerSelectProps) {
  const combobox = useCombobox({ onDropdownClose: () => combobox.resetSelectedOption() });
  // null while not typing; the input then shows the selected value.
  const [search, setSearch] = useState<string | null>(null);

  const options = makerOptions(...knownMakers, value);
  const query = search?.trim() ?? "";
  const filtered = query
    ? options.filter((m) => m.toLowerCase().includes(query.toLowerCase()))
    : options;
  const canAdd = query !== "" && !options.some((m) => m.toLowerCase() === query.toLowerCase());

  const finish = () => {
    setSearch(null);
    combobox.closeDropdown();
  };

  return (
    <Combobox
      store={combobox}
      onOptionSubmit={(option) => {
        onChange(option === ADD_OPTION ? query : option);
        finish();
      }}
    >
      <Combobox.Target>
        <InputBase
          label={label}
          required={required}
          error={error}
          rightSection={<Combobox.Chevron />}
          rightSectionPointerEvents="none"
          value={search ?? value}
          placeholder="Select or type a name"
          onClick={() => combobox.openDropdown()}
          onFocus={() => combobox.openDropdown()}
          onBlur={finish}
          onChange={(e) => {
            combobox.openDropdown();
            combobox.updateSelectedOptionIndex();
            setSearch(e.currentTarget.value);
          }}
        />
      </Combobox.Target>
      <Combobox.Dropdown>
        <Combobox.Options>
          {filtered.map((maker) => (
            <Combobox.Option value={maker} key={maker} active={maker === value}>
              {maker}
            </Combobox.Option>
          ))}
          {canAdd && (
            <Combobox.Option value={ADD_OPTION}>
              <IconUserPlus size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />
              Add “{query}”
            </Combobox.Option>
          )}
          {!query && <Combobox.Empty>Type a name to add someone</Combobox.Empty>}
        </Combobox.Options>
      </Combobox.Dropdown>
    </Combobox>
  );
}

const RESOURCE_BASE_URL = "https://resources.drskippy.app/coffee";

export const coffeeResourceUrl = (filename: string) =>
  `${RESOURCE_BASE_URL}/${filename}`;

export const telemetryResourceUrl = (filename: string) =>
  `${RESOURCE_BASE_URL}/telemetry/${filename}`;

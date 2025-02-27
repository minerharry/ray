import { Typography } from "@material-ui/core";
import dayjs from "dayjs";
import React, { useEffect, useState } from "react";

type DurationTextProps = {
  startTime: Date | number;
  endTime?: Date | number | null;
};

/**
 * Component that shows an incrementing duration text.
 * This component will smartly rerender more often depending on the size of the duration.
 */
export const DurationText = ({ startTime, endTime }: DurationTextProps) => {
  // Increments to force a re-render.
  const [, setRerenderCounter] = useState(0);

  // Assume current time, if end time is nullish
  const endTimeToRender = endTime ? endTime : new Date();
  const duration = dayjs.duration(
    dayjs(endTimeToRender).diff(dayjs(startTime)),
  );

  let durationText: string;
  let refreshInterval = 1000;
  if (duration.asSeconds() < 60) {
    durationText = duration.format("s[s]");
  } else if (duration.asSeconds() < 3600) {
    durationText = duration.format("m[m] s[s]");
  } else {
    // Only refresh once per minute
    durationText = duration.format("H[h] m[m]");
    refreshInterval = 60000;
  }

  useEffect(() => {
    if (!endTime) {
      // Only refresh if this is running job
      const timeout = setInterval(() => {
        setRerenderCounter((counter) => counter + 1);
      }, refreshInterval);
      return () => {
        clearInterval(timeout);
      };
    }
  }, [endTime, refreshInterval]);

  return <Typography>{durationText}</Typography>;
};

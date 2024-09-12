#!/usr/bin/env -S nvim -l

-- vim -l benchmark_dir.lua <DIR> <N_PARALLEL> <N_WARMUP> <DURATION_SECS>
--
-- Run a benchmark on DIR.
--
-- We estimate the mean run time of `measure_once.lua DIR N_PARALLEL` by
-- running it N_WARMUP times.
--
-- Then we run it again for DURATION_SECS seconds. The outputs of that second
-- run are concatenated, skipping all headers except the first one, producing
-- a single table.

---@type integer The minimum number of runs
local N_RUNS_MIN = 10

---@param xs number[] non-empty list of numbers
---@return number mean the average of all numbers in xs
local function calc_mean(xs)
  local sum = 0.0
  local count = 0
  for i, x in ipairs(xs) do
    count = i
    sum = sum + x
  end
  if count < 1 then
    error("need at least one measurement: " .. vim.inspect(xs))
  end
  return sum / count
end

---Measure how long it takes to run a function.
---
---@generic T
---@param fun fun(...): `T` function to measure
---@return number time_ms run time of `fun` in milliseconds
---@return T results all return values of `fun`
local function profile(fun, ...)
  local start_ns = vim.loop.hrtime()
  local res = { fun(...) }
  local end_ns = vim.loop.hrtime()
  local time_ms = (end_ns - start_ns) / 1e6
  return time_ms, unpack(res)
end

---Run the measurement script once once.
---
---Errors if the command fails.
---
---@param dir string the directory of org files to pass
---@param n_parallel integer the maxmimum of open files in parallel to pass
---@return number time_ms the run time of the measurement script
---@return string stdout the captured output of the script
local function measure_once_ms(dir, n_parallel)
  local time_ms, obj = profile(function()
    return vim.system({ 'nvim', '--headless', '-l', './measure_once.lua', dir, tostring(n_parallel) }, {
      text = true,
    }):wait()
  end)
  ---@cast obj vim.SystemCompleted
  if obj.code ~= 0 then
    error('measure_once failed: ' .. obj.stderr)
  end
  return time_ms, obj.stdout
end

---Run the profiled script a few times to warm caches and learn its runtime.
---
---@param dir string the directory of org files to pass
---@param n_parallel integer the maxmimum of open files in parallel to pass
---@param n_warmup integer how many times to run the script
---@return number time_ms the *average* run time of the script
local function warmup(dir, n_parallel, n_warmup)
  local tally = {}
  for _ = 1, n_warmup do
    tally[#tally + 1] = measure_once_ms(dir, n_parallel)
  end
  return calc_mean(tally)
end

---Run the actual benchmark
---
---@param dir string the directory of org files to pass
---@param n_parallel integer the maxmimum of open files in parallel to pass
---@param n_runs integer how many times to run the script
---@return string[] lines The table concatenated from all runs.
local function benchmark(dir, n_parallel, n_runs)
  local lines = nil
  for _ = 1, n_runs do
    local _, stdout = measure_once_ms(dir, n_parallel)
    local lines_run = vim.split(stdout, '\n', { plain = true, trimempty = true })
    if lines then
      -- Only copy the header once.
      vim.list_extend(lines, lines_run, 2)
    else
      lines = lines_run
    end
  end
  if not lines or #lines == 0 then
    error("no output produced")
  end
  return lines
end

---@param argv string[]
local function main(argv)
  if #argv ~= 4 then
    print('usage:', argv[0], '<DIR> <N_PARALLEL> <N_WARMUP> <DURATION_SECS>')
    print('\n')
    print('Run a benchmark on DIR.')
    print('\n')
    print('We estimate the mean run time of `measure_once.lua DIR N_PARALLEL` by')
    print('running it N_WARMUP times.')
    print('\n')
    print('Then we run it again for DURATION_SECS seconds. The outputs of that second')
    print('run are concatenated, skipping all headers except the first one, producing')
    print('a single table.\n')
    os.exit(1)
  end

  local dir = argv[1]
  if vim.fn.isdirectory(dir) == 0 then
    error('not a directory: ' .. dir)
  end

  local n_parallel = math.floor(tonumber(argv[2]) or 0)
  if n_parallel < 1 then
    error("N_PARALLEL must be at least 1: " .. tostring(n_parallel))
  end

  local n_warmup = math.floor(tonumber(argv[3]) or 0)
  if n_warmup < N_RUNS_MIN then
    error("N_WARMUP must be at least 10: " .. tostring(n_warmup))
  end

  local duration_s = tonumber(argv[4] or 0)
  if duration_s < 1 then
    error("DURATION_SECS must be at least 1: " .. tostring(duration_s))
  end

  local expected_duration_ms = 1000.0 * duration_s
  local run_duration_ms = warmup(dir, n_parallel, n_warmup)
  local expected_n_runs = math.floor(expected_duration_ms / run_duration_ms)
  local n_runs = math.max(N_RUNS_MIN, expected_n_runs)
  local output = benchmark(dir, n_parallel, n_runs)
  for _, line in ipairs(output) do
    io.write(line, '\n')
  end
end

main(_G.arg)

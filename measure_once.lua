#!/usr/bin/env -S nvim -l

-- vim -l measure_once.lua <DIR> <N_PARALLEL>
--
-- load all org files in DIR, open N_PARALLEL at max in parallel.
--
-- Report file count, time spent loading, and time spent in `setup()`.

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

---@param argv string[]
local function main(argv)
  if #argv ~= 2 then
    print('usage:', argv[0], '<DIR> <N_PARALLEL>')
    print('\n')
    print('load all org files in DIR, open N_PARALLEL at max in parallel.')
    print('\n')
    print('Report file count, time spent loading, and time spent in `setup()`.\n')
    os.exit(1)
  end

  local dir = argv[1]
  if vim.fn.isdirectory(dir) == 0 then
    error('not a directory: ' .. dir)
  end

  local n_parallel = tonumber(argv[2]) or 0
  if n_parallel < 1 then
    error("N_PARALLEL must be at least 1: " .. tostring(n_parallel))
  end

  vim.opt.rtp:prepend(vim.fn.getcwd())

  local time_setup_ms, org = profile(function()
    return require 'orgmode'.setup {
      org_agenda_files = {
        vim.fs.joinpath(dir, '**', '*.org')
      },
      _experimental_org_files_throttle = math.max(n_parallel, 1),
    }
  end)
  ---@cast org Org

  if rawget(org, 'files') then
    error('files already exist')
  end
  if org.initialized then
    error('org already initialized')
  end

  local time_ms, count = profile(function()
    return #vim.tbl_keys(org.files.files)
  end)
  ---@cast count integer

  io.write(
    "n_files\tn_parallel\ttime_ms\tsetup_ms\n",
    ("%d\t%d\t%.2f\t%.2f\n"):format(count, n_parallel, time_ms, time_setup_ms)
  )
end

main(_G.arg)

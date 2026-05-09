function run_phase0_smoke()
%RUN_PHASE0_SMOKE  WP0.4 sub-task 2 - Phase-0 smoke test.
%
%   Loads the canonical 720-case dataset (built by build_dataset.m if
%   the .mat is missing), picks the noiseless representative cell at
%   alpha = 0.5, R_x = 1000 ohm, runs faultloc_optimiser, and asserts
%   the relative location error is below 0.1 %.  Exits with code 0 on
%   pass and code 1 on failure (suitable for `matlab -batch`).

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    addpath(fullfile(here, 'utils'));

    data_path = fullfile(here, 'data', 'dataset_720.mat');
    if ~isfile(data_path)
        fprintf('run_phase0_smoke: dataset_720.mat missing - building it...\n');
        build_dataset(data_path);
    end
    S = load(data_path);

    % Locate the noiseless cell at (alpha=0.5, R_x=1000).
    target_alpha = 0.5;
    target_Rx    = 1000;
    cell = find( ...
        abs(S.grid_alpha - target_alpha) < 1e-9 & ...
        abs(S.grid_Rx    - target_Rx)    < 1e-9 & ...
        isinf(S.grid_SNR_V)                    & ...
        isinf(S.grid_SNR_I), 1);
    assert(~isempty(cell), ...
        'run_phase0_smoke: noiseless cell (alpha=0.5, Rx=1000) not found');

    fprintf('run_phase0_smoke: representative cell = #%d\n', cell);
    fprintf('  true (alpha, R_x) = (%.3f, %.1f)\n', ...
            S.grid_alpha(cell), S.grid_Rx(cell));

    [theta_hat, info] = faultloc_optimiser(S.H_meas(cell));
    fprintf('  est  (alpha, R_x) = (%.6f, %.3f)  J_min = %.3e  cpu = %.3fs\n', ...
            theta_hat(1), theta_hat(2), info.J_min, info.cpu_time_s);

    rel_err = abs(theta_hat(1) - target_alpha) / target_alpha;
    fprintf('  relative location error = %.4f %%\n', rel_err * 100);

    if rel_err < 1e-3
        fprintf('PHASE0 SMOKE: PASS (loc err %.4f %% < 0.100 %%)\n', rel_err*100);
        if usejava('jvm') == 0 || batchStartupOptionUsed
            exit(0);
        end
    else
        fprintf(2, 'PHASE0 SMOKE: FAIL (loc err %.4f %% >= 0.100 %%)\n', ...
                rel_err*100);
        if usejava('jvm') == 0 || batchStartupOptionUsed
            exit(1);
        else
            error('faultloc:smokeFail', 'location error above 0.1 %%');
        end
    end
end

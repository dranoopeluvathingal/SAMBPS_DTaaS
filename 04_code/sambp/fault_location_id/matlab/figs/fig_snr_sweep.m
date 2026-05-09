function fig_snr_sweep()
%FIG_SNR_SWEEP  Mean location error vs SNR_I (current-channel sweep).
%
%   Reproduces Fig.\,3 of v1: mean location error across the 720-case
%   grid, plotted against SNR_I at fixed SNR_V values.  Saves
%   outputs/fig_snr_sweep.pdf.

    here = fileparts(mfilename('fullpath'));
    addpath(fullfile(here, '..'));
    addpath(fullfile(here, '..', 'utils'));
    out_dir = fullfile(here, '..', '..', 'outputs');
    if ~exist(out_dir, 'dir'), mkdir(out_dir); end

    data_path = fullfile(here, '..', 'data', 'dataset_720.mat');
    if ~isfile(data_path), build_dataset(data_path); end
    S = load(data_path);

    SNR_V_levels = [20 30 40 Inf];
    SNR_I_levels = [20 30 40 Inf];
    err_pct = nan(numel(SNR_V_levels), numel(SNR_I_levels));

    for iv = 1:numel(SNR_V_levels)
        for ii = 1:numel(SNR_I_levels)
            mask = S.grid_SNR_V == SNR_V_levels(iv) ...
                 & S.grid_SNR_I == SNR_I_levels(ii);
            idx = find(mask);
            errs = zeros(numel(idx), 1);
            for n = 1:numel(idx)
                k = idx(n);
                theta_hat = faultloc_optimiser(S.H_meas(k));
                errs(n) = abs(theta_hat(1) - S.grid_alpha(k)) / S.grid_alpha(k);
            end
            err_pct(iv, ii) = 100 * mean(errs);
        end
    end

    SNR_I_label = SNR_I_levels;  SNR_I_label(end) = 50;     % plot Inf at 50 dB
    SNR_V_label = SNR_V_levels;  SNR_V_label(end) = 50;

    fig = figure('Visible', 'off');
    hold on;
    for iv = 1:numel(SNR_V_levels)
        if isinf(SNR_V_levels(iv))
            disp_name = 'SNR_V = noiseless';
        else
            disp_name = sprintf('SNR_V = %d dB', SNR_V_levels(iv));
        end
        plot(SNR_I_label, err_pct(iv, :), '-o', ...
             'LineWidth', 1.4, 'DisplayName', disp_name);
    end
    grid on; box on;
    xlabel('Current-channel SNR_I   (dB; 50 = noiseless)');
    ylabel('Mean fault-location error   (%)');
    title('Location error vs SNR_I across 720-case grid');
    legend('Location', 'best');
    set(gca, 'FontSize', 11, 'YScale', 'log');
    out_path = fullfile(out_dir, 'fig_snr_sweep.pdf');
    exportgraphics(fig, out_path, 'ContentType', 'vector');
    close(fig);
    fprintf('wrote %s\n', out_path);
end

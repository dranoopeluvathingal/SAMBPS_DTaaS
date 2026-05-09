function fig_alpha_rx_heatmap()
%FIG_ALPHA_RX_HEATMAP  Per-cell location error over the alpha x R_x plane.
%
%   Reproduces the alpha-Rx panel of Fig.\,6 of v1.  Builds an n_alpha x
%   n_Rx heatmap of mean location error (averaged over the 4 SNR_V x 4
%   SNR_I noise cells per (alpha, R_x) point).  Saves
%   outputs/fig_alpha_rx_heatmap.pdf.

    here = fileparts(mfilename('fullpath'));
    addpath(fullfile(here, '..'));
    addpath(fullfile(here, '..', 'utils'));
    out_dir = fullfile(here, '..', '..', 'outputs');
    if ~exist(out_dir, 'dir'), mkdir(out_dir); end

    data_path = fullfile(here, '..', 'data', 'dataset_720.mat');
    if ~isfile(data_path), build_dataset(data_path); end
    S = load(data_path);

    alphas = unique(S.grid_alpha);
    Rxs    = unique(S.grid_Rx);
    err_pct = zeros(numel(alphas), numel(Rxs));

    for ia = 1:numel(alphas)
        for ir = 1:numel(Rxs)
            mask = (S.grid_alpha == alphas(ia)) ...
                 & (S.grid_Rx    == Rxs(ir));
            idx = find(mask);
            errs = zeros(numel(idx), 1);
            for n = 1:numel(idx)
                k = idx(n);
                theta_hat = faultloc_optimiser(S.H_meas(k));
                errs(n) = abs(theta_hat(1) - S.grid_alpha(k)) / S.grid_alpha(k);
            end
            err_pct(ia, ir) = 100 * mean(errs);
        end
    end

    fig = figure('Visible', 'off');
    imagesc(Rxs, alphas, log10(max(err_pct, 1e-6)));
    colormap(parula); cb = colorbar;
    cb.Label.String = 'log_{10}( mean loc. error / % )';
    set(gca, 'YDir', 'normal', 'XScale', 'log', 'FontSize', 11);
    xlabel('Arc resistance R_x   (\Omega)');
    ylabel('Per-unit fault location \alpha   (--)');
    title(['Mean fault-location error across noise classes ' ...
           '(SNR_V \times SNR_I averaged)']);
    out_path = fullfile(out_dir, 'fig_alpha_rx_heatmap.pdf');
    exportgraphics(fig, out_path, 'ContentType', 'vector');
    close(fig);
    fprintf('wrote %s\n', out_path);
end

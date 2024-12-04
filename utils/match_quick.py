from scipy.optimize import linear_sum_assignment
# from rapidfuzz.distance import Levenshtein
import Levenshtein
from collections import defaultdict
import copy
from utils.match import compute_edit_distance_matrix_new, get_gt_pred_lines, get_pred_category_type
import pdb
import numpy as np
import evaluate
from collections import Counter
from Levenshtein import distance as Levenshtein_distance


def match_gt2pred_quick(gt_items, pred_items, line_type, img_name):

    gt_lines, norm_gt_lines, gt_cat_list, pred_lines, norm_pred_lines= get_gt_pred_lines(gt_items, pred_items, line_type)
    all_gt_indices = set(range(len(norm_gt_lines)))  
    all_pred_indices = set(range(len(norm_pred_lines)))  
    
    if not norm_gt_lines:
        match_list = []
        for pred_idx in range(len(norm_pred_lines)):
            match_list.append({
                'gt_idx': [""],
                'gt': "",
                'pred_idx': [pred_idx],
                'pred': pred_lines[pred_idx],
                'gt_position': "",
                'pred_position': pred_items[pred_idx]['position'][0],
                'norm_gt': "",
                'norm_pred': norm_pred_lines[pred_idx],
                'gt_category_type': "",
                'pred_category_type': get_pred_category_type(pred_idx, pred_items),
                'gt_attribute': [{}],
                'edit': 1,
                'img_id': img_name
            })
        return match_list
    elif not norm_pred_lines:
        match_list = []
        for gt_idx in range(len(norm_gt_lines)):
            match_list.append({
                'gt_idx': [gt_idx],
                'gt': gt_lines[gt_idx],
                'pred_idx': [""],
                'pred': "",
                'gt_position': [gt_items[gt_idx].get('order') if gt_items[gt_idx].get('order') else gt_items[gt_idx].get('position', [""])[0]],
                'pred_position': "",
                'norm_gt': norm_gt_lines[gt_idx],
                'norm_pred': "",
                'gt_category_type': gt_cat_list[gt_idx],
                'pred_category_type': "",
                'gt_attribute': [gt_items[gt_idx].get("attribute", {})],
                'edit': 1,
                'img_id': img_name
            })
        return match_list
    elif len(norm_gt_lines) == 1 and len(norm_pred_lines) == 1:
        edit_distance = Levenshtein_distance(norm_gt_lines[0], norm_pred_lines[0])
        normalized_edit_distance = edit_distance / max(len(norm_gt_lines[0]), len(norm_pred_lines[0]))
        return [{
            'gt_idx': [0],
            'gt': gt_lines[0],
            'pred_idx': [0],
            'pred': pred_lines[0],
            'gt_position': [gt_items[0].get('order') if gt_items[0].get('order') else gt_items[0].get('position', [""])[0]],
            'pred_position': pred_items[0]['position'][0],
            'norm_gt': norm_gt_lines[0],
            'norm_pred': norm_pred_lines[0],
            'gt_category_type': gt_cat_list[0],
            'pred_category_type': get_pred_category_type(0, pred_items),
            'gt_attribute': [gt_items[0].get("attribute", {})],
            'edit': normalized_edit_distance,
            'img_id': img_name
        }]
 
    cost_matrix = compute_edit_distance_matrix_new(norm_gt_lines, norm_pred_lines)
    
    matched_col_idx, row_ind, cost_list = cal_final_match(cost_matrix, norm_gt_lines, norm_pred_lines)
    
    gt_lens_dict, pred_lens_dict = initialize_indices(norm_gt_lines, norm_pred_lines)
    
    matches, unmatched_gt_indices, unmatched_pred_indices = process_matches(matched_col_idx, row_ind, cost_list, norm_gt_lines, norm_pred_lines, pred_lines)
    
    matching_dict = fuzzy_match_unmatched_items(unmatched_gt_indices, norm_gt_lines, norm_pred_lines)
    
    final_matches = merge_matches(matches, matching_dict)
    
    recalculate_edit_distances(final_matches, gt_lens_dict, norm_gt_lines, norm_pred_lines)
    
    converted_results = convert_final_matches(final_matches, norm_gt_lines, norm_pred_lines)
    
    merged_results = merge_duplicates_add_unmatched(converted_results, norm_gt_lines, norm_pred_lines, gt_lines, pred_lines, all_gt_indices, all_pred_indices)

    for entry in merged_results:
            entry['gt_idx'] = [entry['gt_idx']] if not isinstance(entry['gt_idx'], list) else entry['gt_idx']
            entry['pred_idx'] = [entry['pred_idx']] if not isinstance(entry['pred_idx'], list) else entry['pred_idx']
            entry['gt_position'] = [gt_items[_].get('order') if gt_items[_].get('order') else gt_items[_].get('position', [""])[0] for _ in entry['gt_idx']] if entry['gt_idx'] != [""] else [""]
            entry['pred_position'] = pred_items[entry['pred_idx'][0]]['position'][0] if entry['pred_idx'] != [""] else "" 
            entry['gt'] = ''.join([gt_lines[_] for _ in entry['gt_idx']]) if entry['gt_idx'] != [""] else ""
            entry['pred'] = ''.join([pred_lines[_] for _ in entry['pred_idx']]) if entry['pred_idx'] != [""] else ""
            entry['norm_gt'] = ''.join([norm_gt_lines[_] for _ in entry['gt_idx']]) if entry['gt_idx'] != [""] else ""
            entry['norm_pred'] = ''.join([norm_pred_lines[_] for _ in entry['pred_idx']]) if entry['pred_idx'] != [""] else ""

            if entry['gt_idx'] != [""]:
                ignore_type = ['figure_caption', 'figure_footnote', 'table_caption', 'table_footnote', 'code_algorithm', 'code_algorithm_caption', 'header', 'footer', 'page_footnote', 'page_number', 'equation_caption']
                gt_cagegory_clean = [gt_cat_list[_] for _ in entry['gt_idx'] if gt_cat_list[_] not in ignore_type] 
                if gt_cagegory_clean:
                    entry['gt_category_type'] = Counter(gt_cagegory_clean).most_common(1)[0][0] 
                else:
                    entry['gt_category_type'] = Counter([gt_cat_list[_] for _ in entry['gt_idx']]).most_common(1)[0][0] 
            else:
                entry['gt_category_type'] = ""
            entry['pred_category_type'] = get_pred_category_type(entry['pred_idx'][0], pred_items) if entry['pred_idx'] != [""] else ""
            entry['gt_attribute'] = [gt_items[_].get("attribute", {}) for _ in entry['gt_idx']] if entry['gt_idx'] != [""] else [{}] 
            entry['img_id'] = img_name
        
    return merged_results


def merge_duplicates_add_unmatched(converted_results, norm_gt_lines, norm_pred_lines, gt_lines, pred_lines, all_gt_indices, all_pred_indices):
    merged_results = []
    processed_pred = set()
    processed_gt = set()

    for entry in converted_results:
        pred_idx = tuple(entry['pred_idx']) if isinstance(entry['pred_idx'], list) else (entry['pred_idx'],)
        if pred_idx not in processed_pred and pred_idx != ("",):
            merged_entry = {
                'gt_idx': [entry['gt_idx']],
                'gt': entry['gt'],
                'pred_idx': entry['pred_idx'],
                'pred': entry['pred'],
                'edit': entry['edit']
            }
            for other_entry in converted_results:
                other_pred_idx = tuple(other_entry['pred_idx']) if isinstance(other_entry['pred_idx'], list) else (other_entry['pred_idx'],)
                if other_pred_idx == pred_idx and other_entry is not entry:
                    merged_entry['gt_idx'].append(other_entry['gt_idx'])
                    merged_entry['gt'] += other_entry['gt']
                    processed_gt.add(other_entry['gt_idx'])
            merged_results.append(merged_entry)
            processed_pred.add(pred_idx)
            processed_gt.add(entry['gt_idx'])

    for entry in converted_results:
        if entry['gt_idx'] not in processed_gt:
            merged_results.append(entry)

    for gt_idx in range(len(norm_gt_lines)):
        if gt_idx not in processed_gt:
            merged_results.append({
                'gt_idx': [gt_idx],
                'gt': gt_lines[gt_idx],
                'pred_idx': [""],
                'pred': "",
                'edit': 1
            })
    return merged_results




def formula_format(formula_matches, img_name):
    return [
        {
            "gt": item["gt"],
            "pred": item["pred"],
            "img_id": f"{img_name}_{i}"
        }
        for i, item in enumerate(formula_matches)
    ]


def merge_lists_with_sublists(main_list, sub_lists):
    main_list_final = list(copy.deepcopy(main_list))
    for sub_list in sub_lists:
        pop_idx = main_list_final.index(sub_list[0])
        for _ in sub_list: 
            main_list_final.pop(pop_idx)
        main_list_final.insert(pop_idx, sub_list) 
    return main_list_final   


def sub_pred_fuzzy_matching(gt, pred):
    
    min_d = float('inf')
    # pos = -1

    gt_len = len(gt)
    pred_len = len(pred)

    if gt_len >= pred_len and pred_len > 0:
        for i in range(gt_len - pred_len + 1):
            sub = gt[i:i + pred_len]
            dist = Levenshtein_distance(sub, pred)/pred_len
            if dist < min_d:
                min_d = dist
                pos = i

        return min_d
    else:
        return False
        
def sub_gt_fuzzy_matching(pred, gt):  
    
    min_d = float('inf')  
    pos = ""  
    matched_sub = ""  
    gt_len = len(gt)  
    pred_len = len(pred)  
    
    if pred_len >= gt_len and gt_len > 0:  
        for i in range(pred_len - gt_len + 1):  
            sub = pred[i:i + gt_len]  
            dist = Levenshtein.distance(sub, gt)  /gt_len
            if dist < min_d:  
                min_d = dist  
                pos = i  
                matched_sub = sub  
        return min_d, pos, gt_len, matched_sub  
    else:  
        return 1, "", gt_len, "" 
        
        
def get_final_subset(subset_certain, subset_certain_cost):
    if not subset_certain or not subset_certain_cost:
        return []  

    subset_turple = sorted([(a, b) for a, b in zip(subset_certain, subset_certain_cost)], key=lambda x: x[0][0])

    group_list = defaultdict(list)
    group_idx = 0
    group_list[group_idx].append(subset_turple[0])

    for item in subset_turple[1:]:
        overlap_flag = False
        for subset in group_list[group_idx]:
            for idx in item[0]:
                if idx in subset[0]:
                    overlap_flag = True
                    break
            if overlap_flag:
                break
        if overlap_flag:
            group_list[group_idx].append(item)
        else:
            group_idx += 1
            group_list[group_idx].append(item)

    final_subset = []
    for _, group in group_list.items():
        if len(group) == 1: 
            final_subset.append(group[0][0])
        else:
            path_dict = defaultdict(list)
            path_idx = 0
            path_dict[path_idx].append(group[0])
            
            for subset in group[1:]:
                new_path = True
                for path_idx_s, path_items in path_dict.items():
                    is_dup = False
                    is_same = False
                    for path_item in path_items:
                        if path_item[0] == subset[0]:
                            is_dup = True
                            is_same = True
                            if path_item[1] > subset[1]:
                                path_dict[path_idx_s].pop(path_dict[path_idx_s].index(path_item))
                                path_dict[path_idx_s].append(subset)
                        else:
                            for num_1 in path_item[0]:
                                for num_2 in subset[0]:
                                    if num_1 == num_2:
                                        is_dup = True
                    if not is_dup:
                        path_dict[path_idx_s].append(subset)
                        new_path = False
                    if is_same:
                        new_path = False
                if new_path:
                    path_idx = len(path_dict.keys())
                    path_dict[path_idx].append(subset)

            saved_cost = float('inf')
            saved_subset = []  
            for path_idx, path in path_dict.items():
                avg_cost = sum([i[1] for i in path]) / len(path)
                if avg_cost < saved_cost:
                    saved_subset = [i[0] for i in path]
                    saved_cost = avg_cost

            final_subset.extend(saved_subset)

    return final_subset

def judge_pred_merge(gt_list, pred_list, threshold=0.6):
    if len(pred_list) == 1:
        return False, False

    cur_pred = ' '.join(pred_list[:-1])
    merged_pred = ' '.join(pred_list)
    
    cur_dist = Levenshtein.distance(gt_list[0], cur_pred) / max(len(gt_list[0]), len(cur_pred))
    merged_dist = Levenshtein.distance(gt_list[0], merged_pred) / max(len(gt_list[0]), len(merged_pred))
    
    if merged_dist > cur_dist:
        return False, False

    cur_fuzzy_dists = [sub_pred_fuzzy_matching(gt_list[0], cur_pred) for cur_pred in pred_list[:-1]]
    if any(dist is False or dist > threshold for dist in cur_fuzzy_dists):
        return False, False

    add_fuzzy_dist = sub_pred_fuzzy_matching(gt_list[0], pred_list[-1])
    if add_fuzzy_dist is False:
        return False, False

    merged_pred_flag = add_fuzzy_dist < threshold
    continue_flag = len(merged_pred) <= len(gt_list[0])

    return merged_pred_flag, continue_flag
    
def deal_with_truncated(cost_matrix, norm_gt_lines, norm_pred_lines):
    matched_first = np.argwhere(cost_matrix < 0.25)
    masked_gt_idx = [i[0] for i in matched_first]
    unmasked_gt_idx = [i for i in range(cost_matrix.shape[0]) if i not in masked_gt_idx]
    masked_pred_idx = [i[1] for i in matched_first]
    unmasked_pred_idx = [i for i in range(cost_matrix.shape[1]) if i not in masked_pred_idx]

    merges_gt_dict = {}
    merges_pred_dict = {}
    merged_gt_subsets = []

    for gt_idx in unmasked_gt_idx:
        check_merge_subset = []
        merged_dist = []

        for pred_idx in unmasked_pred_idx: 
            step = 1
            merged_pred = [norm_pred_lines[pred_idx]]

            while True:
                if pred_idx + step in masked_pred_idx or pred_idx + step >= len(norm_pred_lines):
                    break
                else:
                    merged_pred.append(norm_pred_lines[pred_idx + step])
                    merged_pred_flag, continue_flag = judge_pred_merge([norm_gt_lines[gt_idx]], merged_pred) 
                    if not merged_pred_flag:
                        break
                    else:
                        step += 1
                    if not continue_flag:
                        break

            check_merge_subset.append(list(range(pred_idx, pred_idx + step)))
            matched_line = ' '.join([norm_pred_lines[i] for i in range(pred_idx, pred_idx + step)])
            dist = Levenshtein_distance(norm_gt_lines[gt_idx], matched_line) / max(len(matched_line), len(norm_gt_lines[gt_idx]))
            merged_dist.append(dist)

        if not merged_dist:
            subset_certain = []
            min_cost_idx = ""
            min_cost = float('inf')
        else:
            min_cost = min(merged_dist)
            min_cost_idx = merged_dist.index(min_cost)
            subset_certain = check_merge_subset[min_cost_idx]

        merges_gt_dict[gt_idx] = {
            'merge_subset': check_merge_subset,
            'merged_cost': merged_dist,
            'min_cost_idx': min_cost_idx,
            'subset_certain': subset_certain,
            'min_cost': min_cost
        }

    subset_certain = [merges_gt_dict[gt_idx]['subset_certain'] for gt_idx in unmasked_gt_idx if merges_gt_dict[gt_idx]['subset_certain']]
    subset_certain_cost = [merges_gt_dict[gt_idx]['min_cost'] for gt_idx in unmasked_gt_idx if merges_gt_dict[gt_idx]['subset_certain']]

    subset_certain_final = get_final_subset(subset_certain, subset_certain_cost)

    if not subset_certain_final:  
        return cost_matrix, norm_pred_lines, range(len(norm_pred_lines))

    final_pred_idx_list = merge_lists_with_sublists(range(len(norm_pred_lines)), subset_certain_final)
    final_norm_pred_lines = [' '.join(norm_pred_lines[idx_list[0]:idx_list[-1]+1]) if isinstance(idx_list, list) else norm_pred_lines[idx_list] for idx_list in final_pred_idx_list]

    new_cost_matrix = compute_edit_distance_matrix_new(norm_gt_lines, final_norm_pred_lines)

    return new_cost_matrix, final_norm_pred_lines, final_pred_idx_list
    
def cal_move_dist(gt, pred):
    assert len(gt) == len(pred), 'Not right length'
    step = 0
    for i, gt_c in enumerate(gt):
        if gt_c != pred[i]:
            step += abs(i - pred.index(gt_c))
            pred[i], pred[pred.index(gt_c)] = pred[pred.index(gt_c)], pred[i]
    return step / len(gt)

def cal_final_match(cost_matrix, norm_gt_lines, norm_pred_lines):
    min_indice = cost_matrix.argmax(axis=1)

    new_cost_matrix, final_norm_pred_lines, final_pred_idx_list = deal_with_truncated(cost_matrix, norm_gt_lines, norm_pred_lines)

    row_ind, col_ind = linear_sum_assignment(new_cost_matrix)

    cost_list = [new_cost_matrix[r][c] for r, c in zip(row_ind, col_ind)]
    matched_col_idx = [final_pred_idx_list[i] for i in col_ind]

    return matched_col_idx, row_ind, cost_list

def initialize_indices(norm_gt_lines, norm_pred_lines):
    gt_lens_dict = {idx: len(gt_line) for idx, gt_line in enumerate(norm_gt_lines)}
    pred_lens_dict = {idx: len(pred_line) for idx, pred_line in enumerate(norm_pred_lines)}
    return gt_lens_dict, pred_lens_dict

def process_matches(matched_col_idx, row_ind, cost_list, norm_gt_lines, norm_pred_lines, pred_lines):
    matches = {}
    unmatched_gt_indices = []
    unmatched_pred_indices = []

    for i in range(len(norm_gt_lines)):
        if i in row_ind:
            idx = list(row_ind).index(i)
            pred_idx = matched_col_idx[idx]

            if pred_idx is None or (isinstance(pred_idx, list) and None in pred_idx):
                unmatched_pred_indices.append(pred_idx)
                continue

            if isinstance(pred_idx, list):
                pred_line = ' | '.join(norm_pred_lines[pred_idx[0]:pred_idx[-1]+1])
                ori_pred_line = ' | '.join(pred_lines[pred_idx[0]:pred_idx[-1]+1])
                matched_pred_indices_range = list(range(pred_idx[0], pred_idx[-1]+1))
            else:
                pred_line = norm_pred_lines[pred_idx]
                ori_pred_line = pred_lines[pred_idx]
                matched_pred_indices_range = [pred_idx]

            edit = cost_list[idx]

            if edit > 0.7:
                unmatched_pred_indices.extend(matched_pred_indices_range)
                unmatched_gt_indices.append(i)
            else:
                matches[i] = {
                    'pred_indices': matched_pred_indices_range,
                    'edit_distance': edit,
                }
                for matched_pred_idx in matched_pred_indices_range:
                    if matched_pred_idx in unmatched_pred_indices:
                        unmatched_pred_indices.remove(matched_pred_idx)
        else:
            unmatched_gt_indices.append(i)

    return matches, unmatched_gt_indices, unmatched_pred_indices

def fuzzy_match_unmatched_items(unmatched_gt_indices, norm_gt_lines, norm_pred_lines):
    matching_dict = {}

    for pred_idx, pred_content in enumerate(norm_pred_lines):
        if isinstance(pred_idx, list):
            continue

        matching_indices = []

        for unmatched_gt_idx in unmatched_gt_indices:
            gt_content = norm_gt_lines[unmatched_gt_idx]
            cur_fuzzy_dist_unmatch, cur_pos, gt_lens, matched_field = sub_gt_fuzzy_matching(pred_content, gt_content)
            if cur_fuzzy_dist_unmatch < 0.4:
                matching_indices.append(unmatched_gt_idx)

        if matching_indices:
            matching_dict[pred_idx] = matching_indices

    return matching_dict

def merge_matches(matches, matching_dict):
    final_matches = {}
    processed_gt_indices = set() 

    for gt_idx, match_info in matches.items():
        pred_indices = match_info['pred_indices']
        edit_distance = match_info['edit_distance']

        pred_key = tuple(sorted(pred_indices))

        if pred_key in final_matches:
            if gt_idx not in processed_gt_indices:
                final_matches[pred_key]['gt_indices'].append(gt_idx)
                processed_gt_indices.add(gt_idx)
        else:
            final_matches[pred_key] = {
                'gt_indices': [gt_idx],
                'edit_distance': edit_distance
            }
            processed_gt_indices.add(gt_idx)

    for pred_idx, gt_indices in matching_dict.items():
        pred_key = (pred_idx,) if not isinstance(pred_idx, (list, tuple)) else tuple(sorted(pred_idx))

        if pred_key in final_matches:
            for gt_idx in gt_indices:
                if gt_idx not in processed_gt_indices:
                    final_matches[pred_key]['gt_indices'].append(gt_idx)
                    processed_gt_indices.add(gt_idx)
        else:
            final_matches[pred_key] = {
                'gt_indices': [gt_idx for gt_idx in gt_indices if gt_idx not in processed_gt_indices],
                'edit_distance': None
            }
            processed_gt_indices.update(final_matches[pred_key]['gt_indices'])

    return final_matches
    


def recalculate_edit_distances(final_matches, gt_lens_dict, norm_gt_lines, norm_pred_lines):
    for pred_key, info in final_matches.items():
        gt_indices = sorted(set(info['gt_indices']))

        if not gt_indices:
            info['edit_distance'] = 1
            continue

        if len(gt_indices) > 1:
            merged_gt_content = ''.join(norm_gt_lines[gt_idx] for gt_idx in gt_indices)
            pred_content = norm_pred_lines[pred_key[0]] if isinstance(pred_key[0], int) else ''

            try:
                edit_distance = Levenshtein_distance(merged_gt_content, pred_content)
                normalized_edit_distance = edit_distance / max(len(merged_gt_content), len(pred_content))
            except ZeroDivisionError:
                normalized_edit_distance = 1

            info['edit_distance'] = normalized_edit_distance
        else:
            gt_idx = gt_indices[0]
            pred_content = ' '.join(norm_pred_lines[pred_idx] for pred_idx in pred_key if isinstance(pred_idx, int))

            try:
                edit_distance = Levenshtein_distance(norm_gt_lines[gt_idx], pred_content)
                normalized_edit_distance = edit_distance / max(len(norm_gt_lines[gt_idx]), len(pred_content))
            except ZeroDivisionError:
                normalized_edit_distance = 1

            info['edit_distance'] = normalized_edit_distance
            info['pred_content'] = pred_content


def convert_final_matches(final_matches, norm_gt_lines, norm_pred_lines):
    converted_results = []

    all_gt_indices = set(range(len(norm_gt_lines)))
    all_pred_indices = set(range(len(norm_pred_lines)))

    for pred_key, info in final_matches.items():
        pred_content = ' '.join(norm_pred_lines[pred_idx] for pred_idx in pred_key if isinstance(pred_idx, int))
        
        for gt_idx in sorted(set(info['gt_indices'])):
            result_entry = {
                'gt_idx': int(gt_idx),
                'gt': norm_gt_lines[gt_idx],
                'pred_idx': list(pred_key),
                'pred': pred_content,
                'edit': info['edit_distance']
            }
            converted_results.append(result_entry)
    
    matched_gt_indices = set().union(*[set(info['gt_indices']) for info in final_matches.values()])
    unmatched_gt_indices = all_gt_indices - matched_gt_indices
    matched_pred_indices = set(idx for pred_key in final_matches.keys() for idx in pred_key if isinstance(idx, int))
    unmatched_pred_indices = all_pred_indices - matched_pred_indices

    if unmatched_pred_indices:
        if unmatched_gt_indices:
            distance_matrix = [
                [Levenshtein_distance(norm_gt_lines[gt_idx], norm_pred_lines[pred_idx]) for pred_idx in unmatched_pred_indices]
                for gt_idx in unmatched_gt_indices
            ]

            row_ind, col_ind = linear_sum_assignment(distance_matrix)

            for i, j in zip(row_ind, col_ind):
                gt_idx = list(unmatched_gt_indices)[i]
                pred_idx = list(unmatched_pred_indices)[j]
                result_entry = {
                    'gt_idx': int(gt_idx),
                    'gt': norm_gt_lines[gt_idx],
                    'pred_idx': [pred_idx],
                    'pred': norm_pred_lines[pred_idx],
                    'edit': 1
                }
                converted_results.append(result_entry)

            matched_gt_indices.update(list(unmatched_gt_indices)[i] for i in row_ind)
        else:
            result_entry = {
                'gt_idx': "",
                'gt': '',
                'pred_idx': list(unmatched_pred_indices),
                'pred': ' '.join(norm_pred_lines[pred_idx] for pred_idx in unmatched_pred_indices),
                'edit': 1
            }
            converted_results.append(result_entry)
    else:
        for gt_idx in unmatched_gt_indices:
            result_entry = {
                'gt_idx': int(gt_idx),
                'gt': norm_gt_lines[gt_idx],
                'pred_idx': "",
                'pred': '',
                'edit': 1
            }
            converted_results.append(result_entry)

    return converted_results


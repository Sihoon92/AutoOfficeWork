import os
import argparse
import glob
from utils import get_table_info, initialize_logger, get_dictionary
from agent import REFORCE, schema_linking
from chat import GPTChat, _default_model
from prompt import Prompts
import threading
import concurrent.futures
from sql import SqlEnv
import time

try:
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# Global args and shared state (set in __main__)
args: argparse.Namespace | None = None
prompt_all: Prompts | None = None
dictionaries: list | None = None
task_dict: dict | None = None


def execute(task, table_info, args, csv_save_path, log_save_path, sql_save_path, search_directory, format_csv, sql_data):
    assert prompt_all is not None

    if args.rerun:
        if os.path.exists(os.path.join(search_directory, sql_save_path)):
            return
        else:
            print(f"Rerun: {search_directory}")
    elif os.path.exists(os.path.join(search_directory, sql_save_path)):
        return

    # Remove stale log files
    self_files = glob.glob(os.path.join(search_directory, f'*{log_save_path}*'))
    for self_file in self_files:
        os.remove(self_file)

    # Setup logging
    log_file_path = os.path.join(search_directory, log_save_path)
    logger = initialize_logger(log_file_path)
    logger.info("[Answer format]\n" + format_csv + "\n[Answer format]")
    table_struct = table_info[table_info.find("The table structure information is "):]

    # Initialize DB env
    sql_env = SqlEnv()

    # Initialize chat sessions
    chat_session_pre: GPTChat | None = None
    chat_session: GPTChat | None = None
    if args.model:
        chat_session_pre = GPTChat(args.azure, args.pre_model, temperature=args.temperature)
        chat_session = GPTChat(args.azure, args.pre_model, temperature=args.temperature)

    # Build agent
    agent = REFORCE(args, sql_data, search_directory, prompt_all, sql_env, chat_session_pre, chat_session, sql_data + '/' + log_save_path)

    # Exploration phase
    pre_info, response_pre_txt, max_try = agent.exploration(task, table_struct, table_info, logger)
    if max_try <= 0:
        print(f"{sql_data + '/' + log_save_path} Inadequate preparation, skip")
        return
    print(f"{sql_data + '/' + log_save_path}: chat_session_pre len: {chat_session_pre.get_message_len()}")
    csv_save_path = os.path.join(search_directory, csv_save_path)
    sql_save_path = os.path.join(search_directory, sql_save_path)

    # Self-refine phase
    agent.self_refine(args, logger, task, format_csv, table_struct, table_info, response_pre_txt, pre_info, csv_save_path, sql_save_path)
    agent.sql_env.close_db()


def process_sql_data(sql_data):
    assert args is not None
    assert task_dict is not None
    assert prompt_all is not None

    start_time = time.time()
    chat_session_format: GPTChat | None = None
    if args.model:
        chat_session_format = GPTChat(args.azure, args.pre_model, temperature=args.temperature)
    print(sql_data)

    task = task_dict[sql_data]
    search_directory = os.path.join(args.output_path, sql_data)

    # Create agent object (for path helpers)
    agent_format = REFORCE(args, sql_data, search_directory, prompt_all)

    if not os.path.exists(search_directory):
        os.makedirs(search_directory)

    # Skip if result already exists
    if os.path.exists(agent_format.complete_sql_save_path):
        return

    if not os.path.exists(search_directory):
        os.makedirs(search_directory)

    # Load table schema info
    table_info = get_table_info(args.db_path, sql_data, agent_format.api, clear_des=True)

    # Determine answer format
    try:
        format_csv, chat_session_format = agent_format.format_answer(task, chat_session_format)
    except Exception as e:
        print(f"{sql_data}: LLM connection failed in format_answer: {e}")
        return

    # Skip if context is too long
    if chat_session_format.get_message_len() > 200000:
        print(f"{sql_data} Too long context, skip")
        return

    if args.model_vote:
        num_votes = args.num_votes
        sql_paths = {}
        threads = []

        for i in range(num_votes):
            csv_save_pathi = str(i) + agent_format.csv_save_name
            log_pathi = str(i) + agent_format.log_save_name
            sql_save_pathi = str(i) + agent_format.sql_save_name
            sql_paths[sql_save_pathi] = csv_save_pathi

            thread = threading.Thread(
                target=execute,
                args=(
                    task, table_info, args,
                    csv_save_pathi, log_pathi, sql_save_pathi,
                    search_directory, format_csv, sql_data
                )
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        if "result.sql" not in os.listdir(search_directory):
            if any(file.endswith('.sql') for file in os.listdir(search_directory) if os.path.isfile(os.path.join(search_directory, file))):
                agent_format.vote_result(search_directory, task, chat_session_format, sql_paths, table_info)
            else:
                print(f"{sql_data}: Empty")
    else:
        execute(
            task, table_info, args,
            agent_format.csv_save_name, agent_format.log_save_name, agent_format.sql_save_name,
            search_directory, format_csv, sql_data
        )

    print(f"Time for {sql_data}: {int((time.time() - start_time) // 60)} min")


def main(args_in):
    global args, prompt_all, dictionaries, task_dict
    args = args_in

    if args.task_id:
        if args.task_id not in task_dict:
            print(f"Error: task_id '{args.task_id}' not found in dictionary.")
            return
        dictionaries = [args.task_id]
        task_dict = {args.task_id: task_dict[args.task_id]}

    if args.schema_linking_model:
        chat_session_sl = GPTChat(args.azure, args.schema_linking_model, temperature=args.temperature)
        schema_linking(dictionaries, task_dict, args.db_path, chat_session_sl)
    if args.schema_linking_only:
        return

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.num_workers) as executor:
        list(executor.map(process_sql_data, dictionaries))

    print("Finished")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="ReFoRCE: Text-to-SQL with self-refinement and voting")
    parser.add_argument('--task', type=str, default="snow", choices=["snow", "lite"], help="Dataset type: 'snow' for Snowflake, 'lite' for SQLite")
    parser.add_argument('--db_path', type=str, default="examples", help="Path to examples directory")
    parser.add_argument('--output_path', type=str, default="output/o1-preview-snow-log", help="Path to save output results")
    parser.add_argument('--model', type=str, default=_default_model(), help="Main model name (default: LLM_MODEL env var)")
    parser.add_argument('--pre_model', type=str, default=_default_model(), help="Pre-processing model name (default: LLM_MODEL env var)")
    parser.add_argument('--azure', action="store_true", help="Use Azure OpenAI instead of OpenAI")
    parser.add_argument('--schema_linking_model', type=str, default=None, help="Model for schema linking (optional)")
    parser.add_argument('--schema_linking_only', action="store_true", help="Run schema linking only, skip main inference")
    parser.add_argument('--max_iter', type=int, default=5, help="Maximum self-refinement iterations")
    parser.add_argument('--temperature', type=float, default=1, help="Sampling temperature")
    parser.add_argument('--model_vote', action="store_true", help="Enable majority voting")
    parser.add_argument('--num_votes', type=int, default=3, help="Number of votes for majority voting")
    parser.add_argument('--save_all_results', action="store_true", help="Save all intermediate results")
    parser.add_argument('--rerun', action="store_true", help="Rerun tasks that have no result yet without overwriting")
    parser.add_argument('--num_workers', type=int, default=16, help="Number of parallel worker threads")
    parser.add_argument('--task_id', type=str, default=None, help="단일 태스크만 실행 (예: --task_id local01)")

    args = parser.parse_args()
    prompt_all = Prompts()
    dictionaries, task_dict = get_dictionary(args)
    main(args)
